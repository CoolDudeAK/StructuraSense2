import json

import numpy as np
from flask import Blueprint, jsonify, request

from .. import auth, db
from ..services import dsp, ml, simulator
from ._util import body, fail, fnum

bp = Blueprint("signals", __name__, url_prefix="/api")


def _meta(w):
    return {k: w[k] for k in ("id", "device_id", "structure_id", "ts_ms", "fs", "n", "source", "rms", "peak", "crest", "kurtosis", "dom_freq",
                              "centroid", "damping", "is_baseline", "label", "notes", "sim_damage")}


def _baseline_for(dev_id, source, before_ms=None):
    rows = db.q("SELECT * FROM waveforms WHERE device_id=? AND is_baseline=1 ORDER BY ts_ms", (dev_id,))
    kind = "engineer-set baseline"
    if not rows:
        rows = db.q("SELECT * FROM waveforms WHERE device_id=? AND source=? ORDER BY ts_ms LIMIT 3", (dev_id, source))
        kind = "auto: first 3 captures (assumed healthy)"
    return rows, kind


def _feat(w):
    return {k: w[k] for k in ("rms", "peak", "crest", "kurtosis", "dom_freq", "centroid", "damping")}


def compare_to_baseline(w):
    rows, kind = _baseline_for(w["device_id"], w["source"])
    rows = [r for r in rows if r["id"] != w["id"]]
    if not rows:
        return None
    bf = dsp.median_features([_feat(r) for r in rows])
    last = rows[-1]
    bx, cx = dsp.unpack(last["samples"]), dsp.unpack(w["samples"])
    cmp = dsp.compare(bf, _feat(w), dsp._spectrum(bx - bx.mean(), last["fs"]), dsp._spectrum(cx - cx.mean(), w["fs"]))
    cmp["anomaly"] = ml.anomaly_score(cmp)
    cmp["baseline_kind"], cmp["baseline_count"], cmp["baseline_freq"] = kind, len(rows), bf["dom_freq"]
    cmp["baseline_wave_id"] = last["id"]
    return cmp


@bp.get("/waveforms")
@auth.require("viewer")
def list_waveforms():
    dev, sid = request.args.get("device_id"), request.args.get("structure_id")
    lim = max(1, min(request.args.get("limit", 60, type=int), 500))
    sql, args = "SELECT * FROM waveforms WHERE 1=1", []
    if dev:
        sql += " AND device_id=?"
        args.append(dev)
    if sid:
        sql += " AND structure_id=?"
        args.append(sid)
    sql += " ORDER BY ts_ms DESC LIMIT ?"
    args.append(lim)
    return jsonify([_meta(w) for w in db.q(sql, args)])


@bp.get("/waveforms/<wid>")
@auth.require("viewer")
def get_waveform(wid):
    w = db.one("SELECT * FROM waveforms WHERE id=?", (wid,))
    if not w:
        return fail("not_found", "Capture not found.", 404)
    x = dsp.unpack(w["samples"])
    idx, vals = dsp.ui_waveform(x - x.mean(), 900)
    f, a = dsp.ui_spectrum(x, w["fs"])
    out = {"meta": _meta(w), "waveform": {"t": [round(i / w["fs"], 5) for i in idx], "v": vals},
           "spectrum": {"f": f, "a": a}, "bands": json.loads(w["bands_json"] or "[]")}
    cmp = compare_to_baseline(w)
    out["compare"] = cmp
    if cmp:
        rows, _ = _baseline_for(w["device_id"], w["source"])
        rows = [r for r in rows if r["id"] != w["id"]]
        if rows:
            b = rows[-1]
            bx = dsp.unpack(b["samples"])
            bf, ba = dsp.ui_spectrum(bx, b["fs"])
            out["baseline_spectrum"] = {"f": bf, "a": ba}
    return jsonify(out)


@bp.post("/waveforms/<wid>/baseline")
@auth.require("engineer")
def set_baseline(wid):
    w = db.one("SELECT * FROM waveforms WHERE id=?", (wid,))
    if not w:
        return fail("not_found", "Capture not found.", 404)
    flag = 1 if body().get("is_baseline", True) else 0
    db.update("waveforms", wid, {"is_baseline": flag})
    db.audit(auth.current_user(), "waveform.baseline", "waveform", wid, str(flag))
    simulator.refresh_health(w["structure_id"])
    return jsonify({"ok": True, "is_baseline": flag})


@bp.post("/waveforms/<wid>/label")
@auth.require("engineer")
def set_label(wid):
    lab = body().get("label")
    if lab not in ("healthy", "damaged", None):
        return fail("invalid_label", "Label must be healthy, damaged or empty.")
    db.update("waveforms", wid, {"label": lab})
    return jsonify({"ok": True})


@bp.delete("/waveforms/<wid>")
@auth.require("engineer")
def delete_waveform(wid):
    w = db.one("SELECT structure_id FROM waveforms WHERE id=?", (wid,))
    if not w:
        return fail("not_found", "Capture not found.", 404)
    db.run("DELETE FROM waveforms WHERE id=?", (wid,))
    db.audit(auth.current_user(), "waveform.delete", "waveform", wid)
    simulator.refresh_health(w["structure_id"])
    return jsonify({"ok": True})


@bp.post("/waveforms/simulate")
@auth.require("engineer")
def simulate_capture():
    d = body()
    dev = db.one("SELECT * FROM devices WHERE id=?", (d.get("device_id"),))
    if not dev or dev["channel"] != "waveform":
        return fail("invalid_device", "Pick a vibration device (piezo or accelerometer).")
    try:
        dmg = fnum(d.get("damage", 0), "Damage", 0, 0.8)
    except ValueError as e:
        return fail("invalid", str(e))
    wid = simulator.capture(dev, dmg, baseline=bool(d.get("baseline")), label=d.get("label") if d.get("label") in ("healthy", "damaged") else None,
                            notes="Simulated capture from Signal Lab", temp_c=float(d.get("temp_c", 25)))
    simulator.refresh_health(dev["structure_id"])
    return jsonify({"id": wid}), 201


@bp.post("/signal/analyze")
@auth.require("viewer")
def analyze_samples():
    d = body()
    s = d.get("samples")
    if not isinstance(s, list) or not (64 <= len(s) <= 65536):
        return fail("invalid", "Send 64 to 65536 samples.")
    try:
        fs = fnum(d.get("fs"), "Sample rate", 1, 200000, required=True)
        x = np.array([float(v) for v in s])
        if not np.all(np.isfinite(x)):
            raise ValueError("Samples must be finite numbers.")
    except (ValueError, TypeError) as e:
        return fail("invalid", str(e))
    f = dsp.analyze(x, fs)
    fr, a = dsp.ui_spectrum(x, fs)
    return jsonify({"features": f, "spectrum": {"f": fr, "a": a}})


@bp.get("/devices/<did>/trend")
@auth.require("viewer")
def trend(did):
    dev = db.one("SELECT * FROM devices WHERE id=?", (did,))
    if not dev:
        return fail("not_found", "Device not found.", 404)
    rows = db.q("SELECT * FROM waveforms WHERE device_id=? ORDER BY ts_ms DESC LIMIT ?", (did, min(request.args.get("limit", 120, type=int), 300)))
    rows.reverse()
    out = []
    for w in rows:
        c = compare_to_baseline(w)
        out.append({"id": w["id"], "ts_ms": w["ts_ms"], "dom_freq": w["dom_freq"], "rms": w["rms"], "damping": w["damping"], "source": w["source"],
                    "is_baseline": w["is_baseline"], "label": w["label"],
                    "freq_shift_pct": None if not c else round(c["freq_shift_pct"], 3), "anomaly": None if not c else round(c["anomaly"], 3)})
    return jsonify(out)
