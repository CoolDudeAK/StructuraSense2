"""Data intake from hardware / files. A request is accepted if it carries a valid X-Device-Key for the device,
or if a signed-in engineer sends it (this is how the browser's USB serial connection feeds data in)."""
import csv
import io
import json
import math
import time
from datetime import datetime, timezone

import numpy as np
from flask import Blueprint, jsonify, request

from .. import auth, db, events
from ..services import dsp, impact, simulator
from ._util import body, fail

bp = Blueprint("ingest", __name__, url_prefix="/api/ingest")
MAX_READINGS = 5000
MAX_CSV_BYTES = 8 * 1024 * 1024
_last_refresh = {}


def _actor(dev=None):
    """Returns (ok, device_from_key, user). A device key must match the target device."""
    kd = auth.device_from_key()
    if kd is not None:
        if dev is not None and kd["id"] != dev["id"]:
            return False, None, None
        return True, kd, None
    u = auth.current_user()
    if u and auth.RANK[u["role"]] >= auth.RANK["engineer"]:
        return True, None, u
    return False, None, None


def _deny():
    return fail("unauthorized", "Send a valid X-Device-Key for this device, or sign in as an engineer.", 401)


def _touch(dev, ts, source_type=None):
    f = {"last_seen_ms": ts}
    if source_type and dev["source_type"] == "simulated":
        f["source_type"] = source_type  # the first real packet turns a simulated device into a real one
    db.update("devices", dev["id"], f)


def _maybe_refresh(sid, force=False):
    now = time.time()
    if force or now - _last_refresh.get(sid, 0) > 5:
        _last_refresh[sid] = now
        simulator.refresh_health(sid)


def _resolve_device(did, structure_id=None):
    d = db.one("SELECT * FROM devices WHERE id=?", (did,))
    if d:
        return d
    if structure_id:
        return db.one("SELECT * FROM devices WHERE structure_id=? AND id LIKE ?", (structure_id, f"%-{did}"))
    return None


def _ts(v, default):
    if v is None:
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError("ts_ms must be a number.")
    if not math.isfinite(x):
        raise ValueError("ts_ms must be finite.")
    return int(x if x > 1e11 else x * 1000)


@bp.post("/readings")
def ingest_readings():
    d = body()
    dev = _resolve_device(d.get("device_id") or "", d.get("structure_id"))
    if not dev:
        return fail("not_found", "Unknown device_id. Create the device on the Data Acquisition page first.", 404)
    ok, kd, u = _actor(dev)
    if not ok:
        return _deny()
    items = d.get("readings")
    if items is None and "value" in d:
        items = [{"value": d["value"], "ts_ms": d.get("ts_ms")}]
    if not isinstance(items, list) or not items:
        return fail("invalid", "Send readings as a list: [{\"value\": 12.3, \"ts_ms\": 1700000000000}].")
    if len(items) > MAX_READINGS:
        return fail("too_many", f"At most {MAX_READINGS} readings per request.")
    now = db.now_ms()
    rows, bad = [], 0
    for it in items:
        try:
            v = float(it["value"] if isinstance(it, dict) else it)
            if not math.isfinite(v):
                raise ValueError
            rows.append((dev["id"], _ts(it.get("ts_ms") if isinstance(it, dict) else None, now), v, "live", None))
        except (KeyError, TypeError, ValueError):
            bad += 1
    if not rows:
        return fail("invalid", "No valid readings in the request.")
    db.run_many("INSERT INTO readings(device_id,ts_ms,value,source,batch_id) VALUES(?,?,?,?,?)", rows)
    _touch(dev, max(r[1] for r in rows), "esp32_http" if kd else "manual")
    events.publish("tick", {"structure_id": dev["structure_id"], "ts_ms": now, "sim": None,
                            "readings": [{"device_id": dev["id"], "value": rows[-1][2], "unit": dev["unit"], "source": "live"}]})
    _maybe_refresh(dev["structure_id"])
    return jsonify({"ok": True, "accepted": len(rows), "rejected": bad})


@bp.post("/waveform")
def ingest_waveform():
    d = body()
    dev = _resolve_device(d.get("device_id") or "", d.get("structure_id"))
    if not dev:
        return fail("not_found", "Unknown device_id.", 404)
    ok, kd, u = _actor(dev)
    if not ok:
        return _deny()
    s = d.get("samples")
    if not isinstance(s, list) or not (64 <= len(s) <= 16384):
        return fail("invalid", "samples must be a list of 64 to 16384 numbers.")
    try:
        x = np.array([float(v) for v in s], dtype=float)
        fs = float(d.get("fs") or dev["fs"] or 0)
    except (TypeError, ValueError):
        return fail("invalid", "samples and fs must be numbers.")
    if not np.all(np.isfinite(x)) or fs <= 0 or fs > 200000:
        return fail("invalid", "Samples must be finite and fs must be between 0 and 200000 Hz.")
    cfg = json.loads(dev["config_json"] or "{}")
    if d.get("raw_adc") or cfg.get("raw_adc"):  # ADC counts -> millivolts
        bits, vref = int(cfg.get("adc_bits", 10)), float(cfg.get("vref", 5.0))
        x = x / (2 ** bits - 1) * vref * 1000.0
    f = dsp.analyze(x, fs)
    ts = _ts(d.get("ts_ms"), db.now_ms())
    wid = db.uid()
    db.insert("waveforms", {"id": wid, "device_id": dev["id"], "structure_id": dev["structure_id"], "ts_ms": ts, "fs": fs, "n": len(x),
                            "samples": dsp.pack(x), "source": "live", "rms": f["rms"], "peak": f["peak"], "crest": f["crest"],
                            "kurtosis": f["kurtosis"], "dom_freq": f["dom_freq"], "centroid": f["centroid"], "damping": f["damping"],
                            "bands_json": json.dumps(f["bands"]), "is_baseline": 1 if d.get("baseline") else 0,
                            "label": d.get("label") if d.get("label") in ("healthy", "damaged") else None, "notes": d.get("notes")})
    _touch(dev, ts, "esp32_http" if kd else "arduino_serial")
    events.publish("waveform", {"structure_id": dev["structure_id"], "device_id": dev["id"], "id": wid, "ts_ms": ts, "source": "live"})
    _maybe_refresh(dev["structure_id"], force=True)
    return jsonify({"ok": True, "id": wid, "features": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items() if k != "bands"}})


@bp.post("/serial-lines")
def ingest_serial_lines():
    """Browser USB serial / bridge script forwards raw Arduino lines here.
    Accepts the rig's native formats ('184,126,171' or 'S1:184,S2:126,S3:171') for a structure with 3 piezo channels,
    plus 'S|<device>|<value>' and 'W|<device>|<fs>|v1,v2,...' lines for single devices / raw waveform firmware."""
    d = body()
    sid = d.get("structure_id")
    lines = d.get("lines")
    ok, kd, u = _actor()
    if not ok:
        return _deny()
    if not isinstance(lines, list) or not lines or len(lines) > 2000:
        return fail("invalid", "Send lines as a list of 1-2000 strings.")
    if sid and not db.one("SELECT id FROM structures WHERE id=?", (sid,)):
        return fail("not_found", "Unknown structure_id.", 404)
    now = db.now_ms()
    accepted = rejected = 0
    errors = []
    last_pkt = None
    touched = set()
    for i, ln in enumerate(lines):
        text = ln.get("line") if isinstance(ln, dict) else ln
        ts = _ts(ln.get("ts_ms"), now) if isinstance(ln, dict) else now
        text = (text or "").strip()
        if not text or text.startswith("#"):
            continue
        try:
            if text[:2] in ("S|", "W|"):
                parts = text.split("|")
                dev = _resolve_device(parts[1], sid)
                if not dev:
                    raise ValueError(f"unknown device '{parts[1]}'")
                if text[0] == "S":
                    v = float(parts[2])
                    db.insert("readings", {"device_id": dev["id"], "ts_ms": ts, "value": v, "source": "live", "batch_id": None})
                else:
                    fs = float(parts[2])
                    vals = [float(v) for v in parts[3].split(",") if v.strip()]
                    if len(vals) < 64:
                        raise ValueError("waveform line has fewer than 64 samples")
                    r = ingest_waveform_internal(dev, vals, fs, ts)
                _touch(dev, ts, "arduino_serial")
                touched.add(dev["structure_id"])
            else:
                if not sid:
                    raise ValueError("structure_id is required for 3-sensor packets")
                vals = impact.parse_packet(text)
                impact.write_packet(sid, vals, ts, "live")
                last_pkt = (ts, vals)
                for dev in impact.devices(sid):
                    _touch(dev, ts, "arduino_serial")
                touched.add(sid)
            accepted += 1
        except (ValueError, IndexError) as e:
            rejected += 1
            if len(errors) < 5:
                errors.append(f"line {i+1}: {e}")
    if last_pkt:
        events.publish("p2p", {"structure_id": sid, "ts_ms": last_pkt[0], "s1": last_pkt[1][0], "s2": last_pkt[1][1],
                               "s3": last_pkt[1][2], "source": "live"})
    for s in touched:
        _maybe_refresh(s)
    return jsonify({"ok": True, "accepted": accepted, "rejected": rejected, "errors": errors})


def ingest_waveform_internal(dev, vals, fs, ts):
    x = np.array(vals, dtype=float)
    cfg = json.loads(dev["config_json"] or "{}")
    if cfg.get("raw_adc"):
        x = x / (2 ** int(cfg.get("adc_bits", 10)) - 1) * float(cfg.get("vref", 5.0)) * 1000.0
    f = dsp.analyze(x, fs)
    wid = db.uid()
    db.insert("waveforms", {"id": wid, "device_id": dev["id"], "structure_id": dev["structure_id"], "ts_ms": ts, "fs": fs, "n": len(x),
                            "samples": dsp.pack(x), "source": "live", "rms": f["rms"], "peak": f["peak"], "crest": f["crest"],
                            "kurtosis": f["kurtosis"], "dom_freq": f["dom_freq"], "centroid": f["centroid"], "damping": f["damping"],
                            "bands_json": json.dumps(f["bands"]), "is_baseline": 0, "label": None, "notes": None})
    events.publish("waveform", {"structure_id": dev["structure_id"], "device_id": dev["id"], "id": wid, "ts_ms": ts, "source": "live"})
    return wid


# ---------------------------------------------------------------- CSV import
def _parse_ts(v, fallback_ms):
    v = (v or "").strip()
    if not v:
        return fallback_ms
    try:
        x = float(v)
        return int(x if x > 1e11 else x * 1000)
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        pass
    for fmt in ("%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return int(datetime.strptime(v, fmt).replace(tzinfo=timezone.utc).timestamp() * 1000)
        except ValueError:
            continue
    raise ValueError(f"cannot read time '{v}'")


def _read_csv():
    f = request.files.get("file")
    if not f:
        raise ValueError("Choose a CSV file.")
    raw = f.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise ValueError("The file is larger than 8 MB. Split it into smaller files.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise ValueError("The file needs a header row and at least one data row.")
    return f.filename or "upload.csv", rows


def _detect(header):
    h = [c.strip().lower() for c in header]
    if "device_id" in h and "value" in h:
        return "long"
    if len(header) == 1 or (len(header) == 2 and not any(k in h[0] for k in ("device", "sensor"))
                            and any(k in h[0] for k in ("time", "t", "sec")) and any(k in h[1] for k in ("value", "volt", "mv", "sample", "amp", "acc"))):
        return "waveform"
    return "wide"


@bp.post("/csv/preview")
@auth.require("engineer")
def csv_preview():
    try:
        name, rows = _read_csv()
    except ValueError as e:
        return fail("invalid_file", str(e))
    sid = request.form.get("structure_id")
    ids = {r["id"] for r in db.q("SELECT id FROM devices WHERE structure_id=?", (sid,))} if sid else set()
    header = rows[0]
    return jsonify({"filename": name, "columns": header, "preview": rows[1:6], "rows": len(rows) - 1, "mode_guess": _detect(header),
                    "matching_device_columns": [c for c in header if c.strip() in ids]})


@bp.post("/csv")
@auth.require("engineer")
def csv_import():
    """modes: long (timestamp, device_id, value) | wide (timestamp + one column per device) | waveform (one capture of raw samples)"""
    try:
        name, rows = _read_csv()
    except ValueError as e:
        return fail("invalid_file", str(e))
    sid = request.form.get("structure_id")
    if not db.one("SELECT id FROM structures WHERE id=?", (sid,)):
        return fail("not_found", "Choose the structure these readings belong to.", 404)
    mode = request.form.get("mode") or _detect(rows[0])
    header = [c.strip() for c in rows[0]]
    body_rows = rows[1:]
    now = db.now_ms()
    errors, ok_n, bad_n, per = [], 0, 0, {}
    batch = db.uid()
    out = []

    def err(i, msg):
        nonlocal bad_n
        bad_n += 1
        if len(errors) < 10:
            errors.append(f"row {i+2}: {msg}")

    if mode == "waveform":
        did = request.form.get("device_id")
        dev = _resolve_device(did or "", sid)
        if not dev:
            return fail("not_found", "Pick the device this waveform belongs to.", 404)
        try:
            fs = float(request.form.get("fs") or dev["fs"] or 0)
        except ValueError:
            fs = 0
        col = len(header) - 1
        samples, times = [], []
        for i, r in enumerate(body_rows):
            try:
                samples.append(float(r[col]))
                if len(header) > 1:
                    times.append(float(r[0]))
            except (ValueError, IndexError):
                err(i, "not a number")
        if fs <= 0 and len(times) > 2:
            dts = np.diff(times)
            fs = float(1.0 / np.median(dts)) if np.median(dts) > 0 else 0
        if fs <= 0:
            return fail("fs_required", "Enter the sample rate (Hz), or use a file with a time column.")
        n_per = int(request.form.get("capture_size") or 0) or (len(samples) if len(samples) <= 16384 else 4096)
        n_per = max(64, min(n_per, 16384))
        ts0 = now
        for k in range(0, len(samples) - 63, n_per):
            seg = samples[k:k + n_per]
            if len(seg) < 64:
                break
            f = dsp.analyze(seg, fs)
            wid = db.uid()
            db.insert("waveforms", {"id": wid, "device_id": dev["id"], "structure_id": sid, "ts_ms": ts0 + k, "fs": fs, "n": len(seg),
                                    "samples": dsp.pack(seg), "source": "file", "rms": f["rms"], "peak": f["peak"], "crest": f["crest"],
                                    "kurtosis": f["kurtosis"], "dom_freq": f["dom_freq"], "centroid": f["centroid"], "damping": f["damping"],
                                    "bands_json": json.dumps(f["bands"]), "is_baseline": 0, "label": None, "notes": f"Imported from {name}"})
            ok_n += len(seg)
            per[dev["id"]] = per.get(dev["id"], 0) + 1
        if not ok_n:
            return fail("invalid_file", "No capture could be built. Waveforms need at least 64 numeric samples.")
    else:
        mapping = {}
        if mode == "wide":
            for j, c in enumerate(header[1:], 1):
                dev = _resolve_device(c, sid)
                if dev and dev["structure_id"] == sid:
                    mapping[j] = dev
            if not mapping:
                return fail("no_columns", "None of the column names match a device on this structure. Rename the columns to device ids.")
        for i, r in enumerate(body_rows):
            try:
                ts = _parse_ts(r[0], now + i * 1000)
                if mode == "long":
                    ix_d = [c.lower() for c in header].index("device_id")
                    ix_v = [c.lower() for c in header].index("value")
                    dev = _resolve_device(r[ix_d].strip(), sid)
                    if not dev or dev["structure_id"] != sid:
                        raise ValueError(f"unknown device '{r[ix_d]}'")
                    v = float(r[ix_v])
                    if not math.isfinite(v):
                        raise ValueError("non-finite value")
                    out.append((dev["id"], ts, v, "file", batch))
                    per[dev["id"]] = per.get(dev["id"], 0) + 1
                else:
                    got = False
                    for j, dev in mapping.items():
                        cell = r[j].strip() if j < len(r) else ""
                        if cell == "":
                            continue
                        v = float(cell)
                        if not math.isfinite(v):
                            raise ValueError("non-finite value")
                        out.append((dev["id"], ts, v, "file", batch))
                        per[dev["id"]] = per.get(dev["id"], 0) + 1
                        got = True
                    if not got:
                        raise ValueError("no numeric values")
                ok_n += 1
            except (ValueError, IndexError) as e:
                err(i, str(e))
            if len(out) >= 20000:
                db.run_many("INSERT INTO readings(device_id,ts_ms,value,source,batch_id) VALUES(?,?,?,?,?)", out)
                out = []
        if out:
            db.run_many("INSERT INTO readings(device_id,ts_ms,value,source,batch_id) VALUES(?,?,?,?,?)", out)
        if not ok_n:
            return fail("invalid_file", "No valid rows were found. " + (errors[0] if errors else ""))
    db.insert("csv_imports", {"id": batch, "ts_ms": now, "structure_id": sid, "filename": name, "mode": mode, "rows_total": len(body_rows),
                              "rows_ok": ok_n, "rows_rejected": bad_n, "user_id": auth.current_user()["id"]})
    db.audit(auth.current_user(), "csv.import", "structure", sid, f"{name}: {ok_n} ok, {bad_n} rejected")
    for did in per:
        db.update("devices", did, {"last_seen_ms": now})
    _maybe_refresh(sid, force=True)
    return jsonify({"ok": True, "mode": mode, "rows_total": len(body_rows), "rows_ok": ok_n, "rows_rejected": bad_n, "errors": errors,
                    "devices": per, "import_id": batch})


@bp.get("/csv/history")
@auth.require("viewer")
def csv_history():
    sid = request.args.get("structure_id")
    return jsonify(db.q("SELECT * FROM csv_imports" + (" WHERE structure_id=?" if sid else "") + " ORDER BY ts_ms DESC LIMIT 30", (sid,) if sid else ()))
