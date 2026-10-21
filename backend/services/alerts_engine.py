"""Rule-based alert engine + maintenance proposals. Alerts are decision support: engineers acknowledge,
resolve and sign off. Nothing here closes a safety issue automatically except when the measured condition clears
on an alert nobody has acknowledged yet (status 'cleared')."""
import json
import threading

import requests

from .. import db, events
from . import cloud_sync

DEFAULT_THRESHOLDS = {
    "freq_drop_warn_pct": 3.0, "freq_drop_crit_pct": 6.0,
    "anomaly_warn": 0.6,
    "crack_warn_mm": 0.3, "crack_crit_mm": 1.0, "crack_warn_area_pct": 3.0, "crack_crit_area_pct": 8.0,
    "strain_warn_ratio": 0.8, "strain_crit_ratio": 1.0,
    "fatigue_warn_pct_yr": 2.0, "fatigue_crit_pct_yr": 5.0,
    "deflection_warn_ratio": 0.8, "deflection_crit_ratio": 1.0,
    "moisture_warn_pct": 10.0, "moisture_crit_pct": 14.0,
    "health_warn": 60.0, "health_crit": 40.0,
    "rf_warn_pct": 2.0, "rf_crit_pct": 5.0,
    "offline_after_s": 300,
}

TEMPLATES = {
    "freq_shift": ("Targeted NDT and support check",
                   "Dominant frequency is below baseline. Run UPV and rebound-hammer survey on the affected span and inspect bearings and cross-girder connections.", 85000),
    "crack_width": ("Crack mapping and repair assessment",
                    "Map the crack, monitor width with a crack gauge, and assess epoxy injection or sealing. Check cover and corrosion at the location.", 60000),
    "strain": ("Review load restrictions and verify strain gauge",
               "Peak strain is high against the configured limit. Verify the gauge, review traffic restrictions and check the nearest support details.", 30000),
    "fatigue": ("Inspect fatigue-sensitive details",
                "Projected fatigue life consumption is high. Inspect rebar splices, bearing seats and welded details on the affected girder.", 90000),
    "deflection": ("Level survey and load-test review",
                   "Deflection is approaching the allowable. Carry out a precise level survey and review a controlled load test.", 120000),
    "moisture": ("Waterproofing and drainage inspection",
                 "Moisture is rising. Inspect deck waterproofing, expansion joints and drainage; sample for chlorides and carbonation depth.", 70000),
    "wim_overload": ("Inspect after heavy-vehicle event",
                     "A vehicle above the configured weight limit crossed. Inspect bearings and the deck underside near the strain gauges.", 25000),
    "impact_deviation": ("Visual inspection after impact-response change",
                         "Impact-trial response differs from the intact baseline. Inspect the specimen/structure visually, check sensor mounting, and repeat the trial.", 5000),
    "rf_discontinuity": ("Targeted NDT where the RF coil detuned",
                         "The embedded RF coil's resonance has moved away from its baseline, which can mean an internal void, crack or moisture. This sensor is experimental: confirm with UPV, rebound hammer or GPR before acting.", 40000),
    "health_band": ("Detailed engineering inspection",
                    "The health score has fallen into a band that calls for inspection. Schedule a detailed inspection and review the contributing sensors.", 150000),
}


def thresholds():
    t = dict(DEFAULT_THRESHOLDS)
    t.update(db.get_setting("thresholds", {}) or {})
    return t


def _origin(mix):
    live = mix.get("live", 0) + mix.get("file", 0)
    if live == 0:
        return "sim"
    return "live" if mix.get("sim", 0) == 0 else "mixed"


def _sev(v, warn, crit):
    if v >= crit:
        return "critical"
    if v >= warn:
        return "warning"
    return None


def _conditions(sid, res, t):
    """Return {dedupe_key: dict(kind, severity, title, message, value, threshold, zone, device)}."""
    out = {}
    m = res["metrics"]

    def add(kind, sev, title, msg, value, thr, zone=None, device=None):
        if not sev:
            return
        out[f"{sid}:{kind}:{device or zone or ''}"] = dict(kind=kind, severity=sev, title=title, message=msg,
                                                            value=value, threshold=thr, zone=zone, device=device)

    for v in m["vibration"]:
        if v.get("score") is None:
            continue
        drop = max(0.0, -v["freq_shift_pct"])
        s = _sev(drop, t["freq_drop_warn_pct"], t["freq_drop_crit_pct"])
        add("freq_shift", s, f"Natural frequency down {drop:.1f}%",
            f"{v['device_id']}: {v['note']}. A falling frequency indicates loss of stiffness.", round(drop, 2),
            t["freq_drop_warn_pct"], v.get("zone_id"), v["device_id"])
        if v["anomaly"] >= t["anomaly_warn"] and not s:
            add("anomaly", "warning", "Unusual vibration signature",
                f"{v['device_id']}: anomaly score {v['anomaly']:.2f} against the healthy baseline.", v["anomaly"],
                t["anomaly_warn"], v.get("zone_id"), v["device_id"])
    for im in m.get("impact", []):
        if im["status"] in ("POSSIBLE ANOMALY", "URGENT REVIEW"):
            add("impact_deviation", "critical" if im["status"] == "URGENT REVIEW" else "warning",
                f"Impact response {im['combined_score']:.0f}% from baseline ({im['status'].title()})",
                f"Latest {im['condition'].lower()} trial differs from the intact baseline. This shows a change in vibration response, "
                "not a crack location or width. Inspect the specimen visually.", round(im["combined_score"], 1),
                t.get("impact_warn_pct", 20.0))
    for c in m["cracks"]:
        if not c["detected"]:
            continue
        if c["calibrated"] and c["max_width_mm"] is not None:
            s = _sev(c["max_width_mm"], t["crack_warn_mm"], t["crack_crit_mm"])
            add("crack_width", s, f"Crack {c['max_width_mm']:.2f} mm wide",
                f"Latest image analysis shows a {c['severity']} crack, max width {c['max_width_mm']:.2f} mm.",
                c["max_width_mm"], t["crack_warn_mm"], c["zone_id"])
        else:
            s = _sev(c["area_pct"], t["crack_warn_area_pct"], t["crack_crit_area_pct"])
            add("crack_width", s, f"Crack coverage {c['area_pct']:.1f}% of image (uncalibrated)",
                "Image had no scale, so width could not be measured in mm.", c["area_pct"], t["crack_warn_area_pct"], c["zone_id"])
    for st in m["strain"]:
        add("strain", _sev(st["ratio"], t["strain_warn_ratio"], t["strain_crit_ratio"]),
            f"Strain at {st['ratio']*100:.0f}% of limit", f"{st['device_id']}: peak {st['peak_ue']} µε in the last hour.",
            st["ratio"], t["strain_warn_ratio"], st.get("zone_id"), st["device_id"])
        if st["life_pct_per_year"] is not None:
            add("fatigue", _sev(st["life_pct_per_year"], t["fatigue_warn_pct_yr"], t["fatigue_crit_pct_yr"]),
                f"Fatigue life use {st['life_pct_per_year']:.1f}% per year",
                f"{st['device_id']}: Miner's-rule estimate on observed stress ranges (indicative).",
                st["life_pct_per_year"], t["fatigue_warn_pct_yr"], st.get("zone_id"), st["device_id"])
    for d in m["deflection"]:
        add("deflection", _sev(d["ratio"], t["deflection_warn_ratio"], t["deflection_crit_ratio"]),
            f"Deflection {d['peak_mm']} mm ({d['ratio']*100:.0f}% of allowable)",
            f"{d['device_id']}: allowable {d['allow_mm']} mm.", d["ratio"], t["deflection_warn_ratio"], d.get("zone_id"), d["device_id"])
    for mo in m["moisture"]:
        add("moisture", _sev(mo["pct"], t["moisture_warn_pct"], t["moisture_crit_pct"]),
            f"Moisture {mo['pct']:.1f}%", f"{mo['device_id']} reads high; possible water ingress.", mo["pct"],
            t["moisture_warn_pct"], mo.get("zone_id"), mo["device_id"])
    for r in m.get("rf", []):
        add("rf_discontinuity", _sev(abs(r["delta_pct"]), t["rf_warn_pct"], t["rf_crit_pct"]),
            f"RF coil resonance {r['delta_pct']:+.1f}% from baseline",
            f"{r['device_id']}: {r['freq_khz']} kHz vs baseline {r['f0_khz']} kHz. EXPERIMENTAL sensor - indicates a possible internal discontinuity; verify with NDT.",
            round(abs(r["delta_pct"]), 2), t["rf_warn_pct"], r.get("zone_id"), r["device_id"])
    for w in m["wim"]:
        if w["peak_kn"] >= w["limit_kn"]:
            add("wim_overload", "critical" if w["peak_kn"] >= 1.3 * w["limit_kn"] else "warning",
                f"Vehicle of {w['peak_kn']:.0f} kN crossed", f"Above the configured {w['limit_kn']} kN limit.",
                w["peak_kn"], w["limit_kn"], None, w["device_id"])
    if res["score"] is not None:
        if res["score"] < t["health_warn"]:
            sev = "critical" if res["score"] < t["health_crit"] else "warning"
            add("health_band", sev, f"Health score {res['score']:.0f}: {res['band']}",
                "Overall structural health score has dropped below the proposed inspection threshold.",
                res["score"], t["health_warn"])
    return out


def evaluate(sid, res, historic=False):
    """Create/update/clear alerts for a structure from a fresh health result."""
    t = thresholds()
    at = res["ts_ms"]
    active = _conditions(sid, res, t)
    origin = _origin(res["source_mix"])
    existing = {a["dedupe_key"]: a for a in db.q(
        "SELECT * FROM alerts WHERE structure_id=? AND status IN ('open','acknowledged')", (sid,))}
    created = []
    for key, c in active.items():
        ex = existing.get(key)
        if ex:
            upd = {"value": c["value"], "message": c["message"]}
            if c["severity"] == "critical" and ex["severity"] != "critical":
                upd.update(severity="critical", title=c["title"], ts_ms=at, status="open")
            elif ex["status"] == "open":
                upd["title"] = c["title"]
            db.update("alerts", ex["id"], upd)
            continue
        aid = db.uid()
        row = {"id": aid, "structure_id": sid, "zone_id": c["zone"], "device_id": c["device"], "ts_ms": at,
               "severity": c["severity"], "kind": c["kind"], "title": c["title"], "message": c["message"],
               "value": c["value"], "threshold": c["threshold"], "status": "open", "origin": origin, "dedupe_key": key}
        db.insert("alerts", row)
        cloud_sync.enqueue("alerts", aid)
        created.append(row)
        _propose_task(row)
        if not historic:
            events.publish("alert", row)
            if c["severity"] == "critical":
                _webhook(row)
    for key, ex in existing.items():
        if key not in active and ex["status"] == "open":
            db.update("alerts", ex["id"], {"status": "cleared", "resolved_ms": at,
                                           "resolution_note": "Condition cleared on its own (no engineer action)."})
            cloud_sync.enqueue("alerts", ex["id"])
    return created


def _propose_task(alert):
    tpl = TEMPLATES.get(alert["kind"])
    if not tpl or (alert["kind"] == "health_band" and alert["severity"] != "critical"):
        return
    exists = db.one("SELECT id FROM maintenance_tasks WHERE structure_id=? AND title=? "
                    "AND status IN ('proposed','approved','in_progress')", (alert["structure_id"], tpl[0]))
    if exists:
        return
    tid = db.uid()
    pr = "P1" if alert["severity"] == "critical" else "P2"
    db.insert("maintenance_tasks", {"id": tid, "structure_id": alert["structure_id"], "zone_id": alert["zone_id"],
                                    "created_ms": alert["ts_ms"], "title": tpl[0], "description": tpl[1] + " (Proposed by the rules engine; an engineer must approve.)",
                                    "priority": pr, "status": "proposed", "est_cost_inr": tpl[2], "origin_alert_id": alert["id"]})
    cloud_sync.enqueue("maintenance_tasks", tid)


def _webhook(alert):
    url = db.get_setting("webhook.url")
    if not url:
        return

    def post():
        try:
            s = db.one("SELECT name FROM structures WHERE id=?", (alert["structure_id"],))
            requests.post(url, json={"text": f"[StructuraSense] CRITICAL on {s['name'] if s else alert['structure_id']}: "
                                             f"{alert['title']} - {alert['message']}",
                                     "alert": alert}, timeout=5)
        except Exception:
            pass  # a failing webhook must never break monitoring
    threading.Thread(target=post, daemon=True).start()


def check_offline_devices():
    """Live (non-simulated) devices that went quiet. Called by the simulator's housekeeping tick."""
    t = thresholds()
    now = db.now_ms()
    for d in db.q("SELECT * FROM devices WHERE source_type!='simulated' AND last_seen_ms IS NOT NULL"):
        key = f"{d['structure_id']}:device_offline:{d['id']}"
        gone = now - d["last_seen_ms"] > t["offline_after_s"] * 1000
        ex = db.one("SELECT * FROM alerts WHERE dedupe_key=? AND status IN ('open','acknowledged')", (key,))
        if gone and not ex:
            aid = db.uid()
            row = {"id": aid, "structure_id": d["structure_id"], "zone_id": d["zone_id"], "device_id": d["id"], "ts_ms": now,
                   "severity": "warning", "kind": "device_offline", "title": f"{d['name']} stopped reporting",
                   "message": f"No data for over {t['offline_after_s']//60} minutes.", "value": None, "threshold": None,
                   "status": "open", "origin": "live", "dedupe_key": key}
            db.insert("alerts", row)
            events.publish("alert", row)
        elif not gone and ex and ex["status"] == "open":
            db.update("alerts", ex["id"], {"status": "cleared", "resolved_ms": now, "resolution_note": "Device is reporting again."})
