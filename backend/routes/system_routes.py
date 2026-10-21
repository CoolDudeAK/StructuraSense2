import json

import requests
from flask import Blueprint, Response, jsonify, request

from .. import auth, config, db, events
from ..services import alerts_engine, cloud_sync, seed, simulator
from ._util import body, fail, fnum

bp = Blueprint("system", __name__, url_prefix="/api")

PROVENANCE = [
    ("Rig (Arduino UNO + 3 piezo)", "Reads your firmware's 184,126,171 packets over USB (browser or bridge script)", "REAL", "Code runs and is tested with simulated packets here. Live data needs your Arduino."),
    ("Rig (Arduino UNO + 3 piezo)", "Baseline calibration, Intact / Damaged trials, deviation score, 3-level status, history, CSV export", "REAL", "Your Streamlit logic, ported unchanged. Thresholds 20% / 60% are experimental, not engineering limits."),
    ("Rig (Arduino UNO + 3 piezo)", "Demo tap stream and demo trials", "SIMULATED", "Always labelled DEMO/SIMULATION DATA and never mixed silently with live data."),
    ("Data acquisition", "HTTP ingest API with per-device keys (ESP32, any microcontroller or script)", "REAL", "Tested with HTTP clients. ESP32 firmware is provided but was not run on a board."),
    ("Data acquisition", "CSV import: long, wide and raw-waveform formats", "REAL", "Imported rows are tagged 'file'."),
    ("Data acquisition", "Raw waveform capture firmware (Arduino, optional)", "REAL", "Provided; not flashed or tested on a board here."),
    ("Signal processing", "FFT / Welch spectrum, dominant frequency, RMS, kurtosis, damping, baseline comparison", "REAL", "NumPy / SciPy."),
    ("Health index", "Rule-based Structural Health Index over 8 independent sensor channels (strain, WIM load, vibration, deflection, temperature, moisture, RF coil, cracks) with per-zone scores", "REAL", "Bands 80 / 60 / 40 and channel weights are the team's proposals, not a standard. Weights are renormalised over ACTIVE channels."),
    ("Health index", "A single active channel can produce a score; inactive and engineer-disabled channels are shown and left out", "REAL", "Sensor channels tab on every structure."),
    ("Sensors", "RF coil (internal discontinuity) channel", "SIMULATED", "EXPERIMENTAL: no Indian Standard exists. Simulated resonance shift; real coil hardware not built."),
    ("Element Test Lab", "Cube, beam, slab and column tests: per-sensor-channel results, checks against IS 456 / IS 516 / IS 13311 limits, cube group compliance, CSV export", "REAL", "Logic is real and unit-tested. Limits are the team's reading of the codes, flagged 'verify' against the purchased BIS text. Not a test certificate."),
    ("Element Test Lab", "Simulated specimen sensor readings and crack photo", "SIMULATED", "Generated from simple formulas plus noise. Manual mode accepts your real readings; the crack photo is measured by the real detector."),
    ("Health index", "Bridge and flyover sensor streams (strain, LVDT, moisture, WIM, accelerometers)", "SIMULATED", "Demo assets are fictional. Simulated physics, tagged 'sim'."),
    ("Alerts", "Rule engine, acknowledge / resolve with note, maintenance proposals with engineer sign-off", "REAL", "Proposals are drafts until an engineer approves."),
    ("Vision", "Crack detection by classical computer vision with width in mm from a scale", "REAL", "Self-test on synthetic images only. Needs validation on real concrete."),
    ("Vision", "CNN / YOLO crack detector", "FUTURE", "Slot is ready. Needs trained weights (for example on SDNET2018)."),
    ("Models", "Autoencoder for vibration anomalies", "SIMULATED", "A real model trained on simulated healthy data."),
    ("Models", "Random Forest health estimate", "SIMULATED", "A real model trained on simulated labels from the rule framework."),
    ("Models", "Fatigue by rainflow + Miner's rule", "REAL", "Indicative; uses an assumed daily traffic count."),
    ("Models", "LSTM fatigue predictor", "FUTURE", "Needs labelled fatigue data."),
    ("Cloud", "Supabase mirror (queue + upsert)", "EXTERNAL", "Needs your Supabase project and keys. Verified only against a local mock of the API."),
    ("Cloud", "Firebase adapter", "FUTURE", "Adapter interface exists; Firestore not implemented."),
    ("External services", "Site weather (Open-Meteo)", "EXTERNAL", "Needs internet from the server."),
    ("External services", "Critical-alert webhook (Slack-style JSON)", "EXTERNAL", "Needs a webhook URL."),
    ("Hardware not built", "CCTV / drone live video, WIM hardware, strain gauges, LVDTs, RF coil, tuning fork", "FUTURE", "Software side is simulated or slotted. RF coil and tuning fork are research ideas only."),
    ("Security", "Sign-in with roles, hashed passwords, device keys", "REAL", "Prototype-grade. For production add HTTPS, a production web server, backups and an audit review."),
    ("Validation", "Savings claims (60-70% inspection, 30-50% maintenance) and accuracy targets", "FUTURE", "Hypotheses pending the 3-structure pilot."),
]


@bp.get("/health")
def health_check():
    try:
        db.one("SELECT 1")
        ok = True
    except Exception:
        ok = False
    return jsonify({"ok": ok, "version": config.APP_VERSION}), (200 if ok else 503)


@bp.get("/system/status")
@auth.require("viewer")
def status():
    counts = {t: db.one(f"SELECT COUNT(*) n FROM {t}")["n"] for t in ("structures", "devices", "readings", "waveforms", "health_scores", "alerts", "crack_analyses", "impact_trials")}
    return jsonify({"version": config.APP_VERSION, "counts": counts, "sim": simulator.status(), "cloud": cloud_sync.status(),
                    "live_clients": events.subscriber_count(), "webhook_set": bool(db.get_setting("webhook.url"))})


@bp.get("/system/provenance")
@auth.require("viewer")
def provenance():
    return jsonify([{"area": a, "feature": f, "status": s, "note": n} for a, f, s, n in PROVENANCE])


@bp.get("/settings")
@auth.require("viewer")
def get_settings():
    return jsonify({"thresholds": alerts_engine.thresholds(), "defaults": alerts_engine.DEFAULT_THRESHOLDS,
                    "webhook_set": bool(db.get_setting("webhook.url"))})


@bp.put("/settings")
@auth.require("admin")
def put_settings():
    d = body()
    if isinstance(d.get("thresholds"), dict):
        cur = alerts_engine.thresholds()
        for k, v in d["thresholds"].items():
            if k in alerts_engine.DEFAULT_THRESHOLDS:
                try:
                    cur[k] = fnum(v, k, 0, 1e6)
                except ValueError as e:
                    return fail("invalid", str(e))
        db.set_setting("thresholds", cur)
    if "webhook_url" in d:
        u = (d["webhook_url"] or "").strip()
        if u and not u.startswith("https://"):
            return fail("invalid", "The webhook address must start with https://")
        if u:
            db.set_setting("webhook.url", u)
        else:
            db.run("DELETE FROM settings WHERE key='webhook.url'")
    db.audit(auth.current_user(), "settings.update")
    return jsonify({"ok": True})


@bp.post("/system/test-webhook")
@auth.require("admin")
def test_webhook():
    u = db.get_setting("webhook.url")
    if not u:
        return fail("no_webhook", "Set a webhook address first.")
    try:
        r = requests.post(u, json={"text": "[StructuraSense] Test message. Webhook is working."}, timeout=6)
        return jsonify({"ok": r.status_code < 300, "status": r.status_code})
    except requests.RequestException as e:
        return jsonify({"ok": False, "message": f"Could not reach the webhook: {str(e)[:120]}"})


@bp.post("/system/reset")
@auth.require("admin")
def reset():
    if (body().get("confirm") or "") != "RESET":
        return fail("confirm_required", "Type RESET to confirm. All structures, readings and trials will be replaced by the demo data.")
    seed.reset_all()
    db.audit(auth.current_user(), "system.reset")
    return jsonify({"ok": True})


@bp.get("/system/audit")
@auth.require("engineer")
def audit():
    return jsonify(db.q("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (min(request.args.get("limit", 100, type=int), 500),)))


@bp.get("/stream")
@auth.require("viewer")
def stream():
    return Response(events.stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})
