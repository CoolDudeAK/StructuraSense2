import json
import time

from flask import Blueprint, Response, jsonify, request

from .. import auth, db
from ..services import alerts_engine, health, impact, reports, simulator, weather
from ._util import body, fail, fnum

bp = Blueprint("structures", __name__, url_prefix="/api")
KINDS = ("specimen", "bridge", "flyover", "building", "dam")
DEV_KINDS = ("piezo", "accelerometer", "microphone", "strain", "lvdt", "temperature", "moisture", "wim", "camera", "rf_coil")
SRC_TYPES = ("simulated", "arduino_serial", "esp32_http", "csv", "manual")


def device_status(d, now=None):
    now = now or db.now_ms()
    if not d["last_seen_ms"]:
        return "never"
    cfg = json.loads(d["config_json"] or "{}")
    if d["channel"] == "waveform":
        exp = (simulator.WAVE_PROFILES.get(cfg.get("profile", "bridge"), {}).get("every_s", 120) if d["source_type"] == "simulated" else 120)
    elif cfg.get("mode") == "p2p":
        exp = 3
    else:
        exp = 6 if d["source_type"] == "simulated" else 60
    return "online" if now - d["last_seen_ms"] < max(20, exp * 2.5) * 1000 else "idle"


def _dev_out(d, last=None):
    o = {k: d[k] for k in ("id", "structure_id", "zone_id", "name", "kind", "channel", "unit", "source_type", "pos_x", "pos_y", "fs", "last_seen_ms")}
    o["config"] = json.loads(d["config_json"] or "{}")
    o["status"] = device_status(d)
    o["has_key"] = bool(d["api_key_hash"])
    if last is not None:
        o["last"] = last
    return o


def _summary(s):
    sid = s["id"]
    h = health.latest(sid)
    al = {r["severity"]: r["n"] for r in db.q("SELECT severity, COUNT(*) n FROM alerts WHERE structure_id=? AND status IN ('open','acknowledged') GROUP BY severity", (sid,))}
    devs = db.q("SELECT * FROM devices WHERE structure_id=?", (sid,))
    now = db.now_ms()
    mix = {r["source"]: r["n"] for r in db.q("SELECT r.source, COUNT(*) n FROM readings r JOIN devices d ON d.id=r.device_id "
                                              "WHERE d.structure_id=? AND r.ts_ms>? GROUP BY r.source", (sid, now - 3600_000))}
    for w in db.q("SELECT source, COUNT(*) n FROM waveforms WHERE structure_id=? AND ts_ms>? GROUP BY source", (sid, now - 3600_000)):
        mix[w["source"]] = mix.get(w["source"], 0) + w["n"]
    trend = [r["score"] for r in db.q("SELECT score FROM health_scores WHERE structure_id=? AND ts_ms>? ORDER BY ts_ms", (sid, now - 24 * 3600_000))]
    if len(trend) > 48:
        step = len(trend) // 48 + 1
        trend = trend[::step]
    sim = simulator.state_of(sid)
    return {"id": sid, "name": s["name"], "kind": s["kind"], "location": s["location"], "state": s["state"], "lat": s["lat"], "lon": s["lon"],
            "is_demo": bool(s["is_demo"]), "data_mode": s["data_mode"], "span_m": s["span_m"], "material": s["material"],
            "health": None if not h else {"score": h["score"], "band": h["band"], "ts_ms": h["ts_ms"], "coverage": h["coverage"]},
            "trend": trend, "open_alerts": {"critical": al.get("critical", 0), "warning": al.get("warning", 0), "info": al.get("info", 0)},
            "devices": len(devs), "devices_online": sum(1 for d in devs if device_status(d, now) == "online"),
            "sources_1h": mix, "sim": sim, "has_impact_lab": impact.supports(sid)}


@bp.get("/structures")
@auth.require("viewer")
def list_structures():
    return jsonify([_summary(s) for s in db.q("SELECT * FROM structures ORDER BY id")])


@bp.get("/structures/<sid>")
@auth.require("viewer")
def get_structure(sid):
    s = db.one("SELECT * FROM structures WHERE id=?", (sid,))
    if not s:
        return fail("not_found", "Structure not found.", 404)
    out = _summary(s)
    out.update({"description": s["description"], "built_year": s["built_year"], "owner_agency": s["owner_agency"],
                "limits": health.limits_of(s), "zones": db.q("SELECT * FROM zones WHERE structure_id=? ORDER BY idx", (sid,)),
                "health_full": health.latest(sid), "p2p_demo": simulator.p2p_status(sid) if impact.supports(sid) else None})
    last = {}
    for d in db.q("SELECT * FROM devices WHERE structure_id=? ORDER BY id", (sid,)):
        r = db.one("SELECT ts_ms,value,source FROM readings WHERE device_id=? ORDER BY ts_ms DESC LIMIT 1", (d["id"],))
        if d["channel"] == "waveform":
            w = db.one("SELECT ts_ms,dom_freq,rms,source FROM waveforms WHERE device_id=? ORDER BY ts_ms DESC LIMIT 1", (d["id"],))
            r = None if not w else {"ts_ms": w["ts_ms"], "value": w["dom_freq"], "source": w["source"], "note": "dominant frequency (Hz)"}
        last[d["id"]] = r
    out["device_list"] = [_dev_out(d, last.get(d["id"])) for d in db.q("SELECT * FROM devices WHERE structure_id=? ORDER BY id", (sid,))]
    return jsonify(out)


@bp.post("/structures")
@auth.require("engineer")
def create_structure():
    d = body()
    name = (d.get("name") or "").strip()
    if len(name) < 3:
        return fail("invalid_name", "Give the structure a name (at least 3 characters).")
    kind = d.get("kind", "bridge")
    if kind not in KINDS:
        return fail("invalid_kind", f"Kind must be one of: {', '.join(KINDS)}.")
    try:
        lat = fnum(d.get("lat"), "Latitude", -90, 90)
        lon = fnum(d.get("lon"), "Longitude", -180, 180)
        span = fnum(d.get("span_m"), "Span (m)", 0.1, 2000, default=20.0)
    except ValueError as e:
        return fail("invalid", str(e))
    n = (db.one("SELECT COUNT(*) n FROM structures")["n"] or 0) + 1
    sid = f"STR-{n:03d}"
    while db.one("SELECT id FROM structures WHERE id=?", (sid,)):
        n += 1
        sid = f"STR-{n:03d}"
    db.insert("structures", {"id": sid, "name": name, "kind": kind, "location": d.get("location"), "state": d.get("state"), "lat": lat,
                             "lon": lon, "built_year": d.get("built_year"), "material": d.get("material"), "span_m": span,
                             "owner_agency": d.get("owner_agency"), "description": d.get("description"), "is_demo": 0, "data_mode": "all",
                             "limits_json": json.dumps(health.DEFAULT_LIMITS), "created_ms": db.now_ms()})
    names = d.get("zones") if isinstance(d.get("zones"), list) and d.get("zones") else [f"Zone {i}" for i in range(1, 6)]
    for i, zn in enumerate(names[:12]):
        db.insert("zones", {"id": f"{sid}-Z{i+1}", "structure_id": sid, "idx": i, "name": str(zn)[:60], "x0": i / len(names[:12]), "x1": (i + 1) / len(names[:12])})
    db.audit(auth.current_user(), "structure.create", "structure", sid, name)
    return jsonify({"id": sid}), 201


@bp.patch("/structures/<sid>")
@auth.require("engineer")
def patch_structure(sid):
    s = db.one("SELECT * FROM structures WHERE id=?", (sid,))
    if not s:
        return fail("not_found", "Structure not found.", 404)
    d = body()
    f = {}
    for k in ("name", "location", "state", "description", "material", "owner_agency"):
        if k in d:
            f[k] = (str(d[k]).strip() if d[k] is not None else None)
    try:
        for k, lo, hi in (("lat", -90, 90), ("lon", -180, 180), ("span_m", 0.1, 2000)):
            if k in d:
                f[k] = fnum(d[k], k, lo, hi)
    except ValueError as e:
        return fail("invalid", str(e))
    if "data_mode" in d:
        if d["data_mode"] not in ("sim", "live", "all"):
            return fail("invalid_mode", "Data mode must be sim, live or all.")
        f["data_mode"] = d["data_mode"]
    if "limits" in d and isinstance(d["limits"], dict):
        lim = health.limits_of(s)
        for k in health.DEFAULT_LIMITS:
            if k in d["limits"]:
                try:
                    lim[k] = fnum(d["limits"][k], k, 0.001, 1e7)
                except ValueError as e:
                    return fail("invalid", str(e))
        f["limits_json"] = json.dumps(lim)
    db.update("structures", sid, f)
    db.audit(auth.current_user(), "structure.update", "structure", sid, json.dumps({k: v for k, v in f.items() if k != "limits_json"}))
    if "data_mode" in f or "limits_json" in f:
        simulator.refresh_health(sid)
    return jsonify({"ok": True})


@bp.delete("/structures/<sid>")
@auth.require("admin")
def delete_structure(sid):
    if not db.one("SELECT id FROM structures WHERE id=?", (sid,)):
        return fail("not_found", "Structure not found.", 404)
    db.run("DELETE FROM structures WHERE id=?", (sid,))
    db.audit(auth.current_user(), "structure.delete", "structure", sid)
    return jsonify({"ok": True})


@bp.get("/structures/<sid>/health/history")
@auth.require("viewer")
def health_history(sid):
    hours = request.args.get("hours", 72, type=float)
    rows = db.q("SELECT ts_ms,score,band FROM health_scores WHERE structure_id=? AND ts_ms>? ORDER BY ts_ms", (sid, db.now_ms() - int(hours * 3600_000)))
    mp = request.args.get("max_points", 300, type=int)
    if len(rows) > mp:
        step = len(rows) / mp
        rows = [rows[int(i * step)] for i in range(mp)] + [rows[-1]]
    return jsonify(rows)


@bp.get("/structures/<sid>/health")
@auth.require("viewer")
def health_latest(sid):
    h = health.latest(sid)
    return jsonify(h) if h else fail("no_data", "No health score yet. Data is needed first.", 404)


@bp.post("/structures/<sid>/health/recompute")
@auth.require("engineer")
def health_recompute(sid):
    if not db.one("SELECT id FROM structures WHERE id=?", (sid,)):
        return fail("not_found", "Structure not found.", 404)
    res = simulator.refresh_health(sid, force=True)
    res.pop("metrics", None)
    return jsonify(res)


@bp.get("/structures/<sid>/channels")
@auth.require("viewer")
def channels(sid):
    """One row per sensor channel: its own score, whether it is ACTIVE / INACTIVE / DISABLED, and how much it
    contributes to the overall score. The overall score is built only from the active channels."""
    st = db.one("SELECT * FROM structures WHERE id=?", (sid,))
    if not st:
        return fail("not_found", "Structure not found.", 404)
    hres = health.latest(sid) or {"components": {}, "score": None, "coverage": 0, "ts_ms": None, "band": "No data"}
    devs = [_dev_out(d) for d in db.q("SELECT * FROM devices WHERE structure_id=?", (sid,))]
    disabled = set(db.get_setting(f"channels.disabled.{sid}", []) or [])
    out, tot = [], 0.0
    for k, meta in health.CHANNELS.items():
        c = (hres["components"] or {}).get(k) or {}
        kd = [d for d in devs if d["kind"] in meta["kinds"]]
        active = bool(c.get("available")) and k not in disabled
        tot += health.WEIGHTS[k] if active and c.get("score") is not None else 0
        out.append({"key": k, **{x: meta[x] for x in ("device", "parameter", "purpose", "unit")}, "weight": health.WEIGHTS[k],
                    "score": c.get("score"), "band": health.band(c.get("score")) if c.get("score") is not None else "No data",
                    "state": "disabled" if k in disabled else ("active" if active else "inactive"),
                    "why_inactive": None if active or k in disabled else ("No " + meta["device"] + " installed on this structure." if not kd and k != "cracks" else
                                    "No recent data under the current data-source setting (offline, never connected, or filtered out)."),
                    "devices": len(kd), "devices_online": sum(1 for d in kd if d["status"] == "online"),
                    "items": c.get("items", []), "sources": sorted({d["source_type"] for d in kd})})
    for r in out:
        r["contribution"] = round(r["weight"] * r["score"] / tot, 1) if r["state"] == "active" and r["score"] is not None and tot else None
        r["effective_weight_pct"] = round(r["weight"] / tot * 100, 1) if r["state"] == "active" and tot else 0
    return jsonify({"structure_id": sid, "score": hres["score"], "band": hres["band"], "coverage": hres["coverage"], "ts_ms": hres["ts_ms"],
                    "data_mode": st["data_mode"], "channels": out,
                    "formula": "Overall = sum(weight x score) / sum(weight), over ACTIVE channels only."})


@bp.put("/structures/<sid>/channels/<key>")
@auth.require("engineer")
def set_channel(sid, key):
    if not db.one("SELECT id FROM structures WHERE id=?", (sid,)):
        return fail("not_found", "Structure not found.", 404)
    if key not in health.WEIGHTS:
        return fail("invalid", "Unknown channel.")
    enabled = bool(body().get("enabled", True))
    cur = set(db.get_setting(f"channels.disabled.{sid}", []) or [])
    (cur.discard if enabled else cur.add)(key)
    db.set_setting(f"channels.disabled.{sid}", sorted(cur))
    db.audit(auth.current_user(), "channel.enable" if enabled else "channel.disable", "structure", sid, key)
    from ..services import simulator
    simulator.refresh_health(sid, force=True)
    return jsonify({"ok": True, "disabled": sorted(cur)})


@bp.get("/structures/<sid>/readings")
@auth.require("viewer")
def readings(sid):
    dev = request.args.get("device_id")
    d = db.one("SELECT * FROM devices WHERE id=? AND structure_id=?", (dev, sid))
    if not d:
        return fail("not_found", "Device not found on this structure.", 404)
    hours = request.args.get("hours", 6, type=float)
    mp = max(50, min(request.args.get("max_points", 300, type=int), 1500))
    rows = db.q("SELECT ts_ms,value,source FROM readings WHERE device_id=? AND ts_ms>? ORDER BY ts_ms", (dev, db.now_ms() - int(hours * 3600_000)))
    pts = rows
    if len(rows) > mp:
        k = len(rows) / (mp / 2)
        pts, i = [], 0.0
        while int(i) < len(rows):
            seg = rows[int(i):int(i + k) or int(i) + 1]
            if seg:
                lo, hi = min(seg, key=lambda r: r["value"]), max(seg, key=lambda r: r["value"])
                for r in sorted({id(lo): lo, id(hi): hi}.values(), key=lambda r: r["ts_ms"]):
                    pts.append(r)
            i += k
    vals = [r["value"] for r in rows]
    return jsonify({"device": _dev_out(d), "points": [[r["ts_ms"], round(r["value"], 3), r["source"]] for r in pts],
                    "stats": None if not vals else {"n": len(vals), "min": min(vals), "max": max(vals), "mean": sum(vals) / len(vals), "last": vals[-1]}})


@bp.get("/structures/<sid>/weather")
@auth.require("viewer")
def site_weather(sid):
    s = db.one("SELECT lat,lon FROM structures WHERE id=?", (sid,))
    if not s:
        return fail("not_found", "Structure not found.", 404)
    return jsonify(weather.current(s["lat"], s["lon"]))


@bp.get("/structures/<sid>/report")
@auth.require("viewer")
def report(sid):
    if not db.one("SELECT id FROM structures WHERE id=?", (sid,)):
        return fail("not_found", "Structure not found.", 404)
    fmt = request.args.get("format", "html")
    if fmt == "csv":
        return Response(reports.readings_csv(sid, request.args.get("hours", 24, type=float)), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={sid}_readings.csv"})
    if fmt == "json":
        h = health.latest(sid)
        return jsonify({"structure": db.one("SELECT * FROM structures WHERE id=?", (sid,)), "health": h})
    return Response(reports.build_html(sid, auth.current_user()["name"]), mimetype="text/html")


# ---------------------------------------------------------------- devices
@bp.get("/devices")
@auth.require("viewer")
def devices():
    sid = request.args.get("structure_id")
    rows = db.q("SELECT * FROM devices" + (" WHERE structure_id=?" if sid else "") + " ORDER BY structure_id,id", (sid,) if sid else ())
    return jsonify([_dev_out(d) for d in rows])


@bp.post("/devices")
@auth.require("engineer")
def create_device():
    import re
    import secrets
    d = body()
    sid = d.get("structure_id")
    if not db.one("SELECT id FROM structures WHERE id=?", (sid,)):
        return fail("not_found", "Pick an existing structure.", 404)
    did = (d.get("id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_\-]{1,40}", did):
        return fail("invalid_id", "Device id must be 2-41 characters: letters, digits, - or _.")
    if db.one("SELECT id FROM devices WHERE id=?", (did,)):
        return fail("exists", "A device with this id already exists.", 409)
    kind = d.get("kind")
    if kind not in DEV_KINDS:
        return fail("invalid_kind", f"Kind must be one of: {', '.join(DEV_KINDS)}.")
    st = d.get("source_type", "esp32_http")
    if st not in SRC_TYPES:
        return fail("invalid_source", f"Source type must be one of: {', '.join(SRC_TYPES)}.")
    channel = "image" if kind == "camera" else ("waveform" if kind in ("piezo", "accelerometer", "microphone") else "scalar")
    if d.get("channel") in ("waveform", "scalar") and kind != "camera":
        channel = d["channel"]
    try:
        fs = fnum(d.get("fs"), "Sample rate", 1, 100000) if channel == "waveform" else None
    except ValueError as e:
        return fail("invalid", str(e))
    zone = d.get("zone_id")
    if zone and not db.one("SELECT id FROM zones WHERE id=? AND structure_id=?", (zone, sid)):
        return fail("invalid_zone", "That zone does not belong to this structure.")
    key = "ssk_" + secrets.token_urlsafe(24)
    db.insert("devices", {"id": did, "structure_id": sid, "zone_id": zone or None, "name": (d.get("name") or did)[:80], "kind": kind,
                          "channel": channel, "unit": d.get("unit"), "source_type": st, "pos_x": d.get("pos_x"), "pos_y": d.get("pos_y"), "fs": fs,
                          "api_key_hash": auth.hash_key(key), "config_json": json.dumps(d.get("config") if isinstance(d.get("config"), dict) else {}),
                          "created_ms": db.now_ms()})
    db.audit(auth.current_user(), "device.create", "device", did, sid)
    return jsonify({"id": did, "api_key": key, "note": "Copy this key now. It is shown only once."}), 201


@bp.post("/devices/<did>/rotate-key")
@auth.require("engineer")
def rotate_key(did):
    import secrets
    if not db.one("SELECT id FROM devices WHERE id=?", (did,)):
        return fail("not_found", "Device not found.", 404)
    key = "ssk_" + secrets.token_urlsafe(24)
    db.update("devices", did, {"api_key_hash": auth.hash_key(key)})
    db.audit(auth.current_user(), "device.rotate_key", "device", did)
    return jsonify({"id": did, "api_key": key, "note": "Copy this key now. The old key no longer works."})


@bp.patch("/devices/<did>")
@auth.require("engineer")
def patch_device(did):
    d = body()
    if not db.one("SELECT id FROM devices WHERE id=?", (did,)):
        return fail("not_found", "Device not found.", 404)
    f = {k: d[k] for k in ("name", "unit", "pos_x", "pos_y") if k in d}
    if "source_type" in d:
        if d["source_type"] not in SRC_TYPES:
            return fail("invalid_source", "Unknown source type.")
        f["source_type"] = d["source_type"]
    if "zone_id" in d:
        f["zone_id"] = d["zone_id"] or None
    db.update("devices", did, f)
    return jsonify({"ok": True})


@bp.delete("/devices/<did>")
@auth.require("engineer")
def delete_device(did):
    if not db.one("SELECT id FROM devices WHERE id=?", (did,)):
        return fail("not_found", "Device not found.", 404)
    db.run("DELETE FROM devices WHERE id=?", (did,))
    db.audit(auth.current_user(), "device.delete", "device", did)
    return jsonify({"ok": True})
