"""Structural Health Index (0-100).

METHOD (rule-based scoring framework v2) - a transparent, engineer-readable framework, NOT a calibrated
standard. The bands (80/60/40) are StructuraSense's own proposed thresholds from the pitch deck and must be
calibrated against structure-specific baselines during field validation.

Eight independent channels (one per sensor family + crack imaging), each scored 0-100 on its own:
  vibration       accelerometers: dominant-frequency shift vs baseline (stiffness loss) + autoencoder anomaly score
  cracks          camera images: worst crack width per zone (width in mm if calibrated)
  strain_fatigue  strain gauges: peak strain vs limit + Miner's-rule fatigue life consumption rate (indicative)
  deflection      LVDT: peak vs allowable (span / ratio)
  load            WIM: heaviest vehicle vs configured limit + share of overloaded vehicles
  thermal         temperature sensors: daily range and peak (thermal-stress exposure, indicative)
  environment     moisture probes: water ingress
  internal        RF coils: resonant-frequency shift from baseline (EXPERIMENTAL, no code basis)

A channel with no data is INACTIVE: it is left out and the weights of the active channels are renormalised, so even a
single working channel yields a score. `coverage` says how much of the framework weight is active. An engineer can
also switch a channel off (it is then shown as DISABLED and ignored). Which sources (simulated / live / file) feed the score is controlled per structure by data_mode.
"""
import json
import statistics

import numpy as np

from .. import db
from . import dsp, impact, ml

WEIGHTS = {"vibration": 0.25, "cracks": 0.25, "strain_fatigue": 0.12, "deflection": 0.12, "environment": 0.08,
           "load": 0.07, "thermal": 0.05, "internal": 0.06}
LABELS = {"vibration": "Vibration", "cracks": "Cracks", "strain_fatigue": "Strain & fatigue",
          "deflection": "Deflection", "environment": "Moisture", "load": "Traffic load", "thermal": "Temperature",
          "internal": "Internal discontinuity (RF)"}
# What each channel is made of: device family, the parameter it measures, and why (from the project's device table)
CHANNELS = {
    "strain_fatigue": {"device": "Strain gauges", "kinds": ["strain"], "parameter": "Strain", "purpose": "Measure deformation", "unit": "µε"},
    "load": {"device": "WIM sensors", "kinds": ["wim"], "parameter": "Load", "purpose": "Traffic load monitoring", "unit": "kN"},
    "vibration": {"device": "Accelerometers", "kinds": ["accelerometer", "piezo", "microphone"], "parameter": "Vibration", "purpose": "Detect stiffness change", "unit": "Hz"},
    "deflection": {"device": "LVDT sensors", "kinds": ["lvdt"], "parameter": "Deflection", "purpose": "Beam bending measurement", "unit": "mm"},
    "thermal": {"device": "Temperature sensors", "kinds": ["temperature"], "parameter": "Temperature", "purpose": "Thermal stress monitoring", "unit": "°C"},
    "environment": {"device": "Moisture probes", "kinds": ["moisture"], "parameter": "Moisture", "purpose": "Detect water infiltration", "unit": "%"},
    "internal": {"device": "RF coils (experimental)", "kinds": ["rf_coil"], "parameter": "Internal discontinuity", "purpose": "Detect internal defects", "unit": "kHz"},
    "cracks": {"device": "Cameras / photos", "kinds": ["camera"], "parameter": "Surface cracks", "purpose": "Measure crack width and length", "unit": "mm"},
}
BANDS = [(80, "Optimal"), (60, "Routine check"), (40, "Inspection needed"), (-1, "Urgent repair")]
METHOD = "rule-based-framework-v2"
SOURCES = {"sim": ("sim",), "live": ("live", "file"), "all": ("sim", "live", "file")}

DEFAULT_LIMITS = {"strain_limit_ue": 400, "deflection_ratio": 800, "wim_limit_kn": 400, "cycles_per_day": 20000}


def band(score):
    if score is None:
        return "No data"
    for t, name in BANDS:
        if score >= t:
            return name
    return "Urgent repair"


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def interp(x, pts):
    xs, ys = zip(*pts)
    return float(np.interp(x, xs, ys))


def combine(comps: dict):
    """comps: {name: score|None} -> (score, coverage)."""
    tot = sum(WEIGHTS[k] for k, v in comps.items() if v is not None and k in WEIGHTS)
    if tot <= 0:
        return None, 0.0
    s = sum(WEIGHTS[k] * v for k, v in comps.items() if v is not None and k in WEIGHTS) / tot
    return float(s), float(tot)


def _src_sql(mode):
    return "(" + ",".join(f"'{s}'" for s in SOURCES.get(mode, SOURCES["all"])) + ")"


def limits_of(s):
    out = dict(DEFAULT_LIMITS)
    try:
        out.update(json.loads(s.get("limits_json") or "{}"))
    except ValueError:
        pass
    return out


def _agg(scores):
    return 0.6 * min(scores) + 0.4 * (sum(scores) / len(scores))


# ------------------------------------------------------------------ vibration
def vibration_for_device(dev, at_ms, mode):
    src = _src_sql(mode)
    cur = db.one(f"SELECT * FROM waveforms WHERE device_id=? AND ts_ms<=? AND source IN {src} ORDER BY ts_ms DESC LIMIT 1",
                 (dev["id"], at_ms))
    if not cur:
        return None
    base_rows = db.q(f"SELECT * FROM waveforms WHERE device_id=? AND is_baseline=1 AND ts_ms<=? AND source IN {src} ORDER BY ts_ms",
                     (dev["id"], at_ms))
    kind = "baseline set by engineer"
    if not base_rows:
        base_rows = db.q(f"SELECT * FROM waveforms WHERE device_id=? AND ts_ms<=? AND source=? ORDER BY ts_ms LIMIT 3",
                         (dev["id"], at_ms, cur["source"]))
        kind = "auto baseline = first 3 captures (assumed healthy)"
    base_rows = [b for b in base_rows if b["id"] != cur["id"]]
    if not base_rows:
        return {"device_id": dev["id"], "wave_id": cur["id"], "ts_ms": cur["ts_ms"], "score": None,
                "note": "Needs a baseline capture before changes can be measured."}
    bf = dsp.median_features([_feat(b) for b in base_rows])
    cf = _feat(cur)
    bs = dsp._spectrum(dsp.unpack(base_rows[-1]["samples"]) - dsp.unpack(base_rows[-1]["samples"]).mean(), base_rows[-1]["fs"])
    cs = dsp._spectrum(dsp.unpack(cur["samples"]) - dsp.unpack(cur["samples"]).mean(), cur["fs"])
    cmp = dsp.compare(bf, cf, bs, cs)
    an = ml.anomaly_score(cmp)
    drop = max(0.0, -cmp["freq_shift_pct"])
    pen_f = _clamp((drop - 1.0) / 9.0) * 100
    score = 100 - (0.7 * pen_f + 0.3 * an * 100)
    return {"device_id": dev["id"], "wave_id": cur["id"], "ts_ms": cur["ts_ms"], "score": round(score, 1),
            "freq_shift_pct": round(cmp["freq_shift_pct"], 2), "anomaly": round(an, 3),
            "baseline_freq": round(bf["dom_freq"], 3), "freq": round(cf["dom_freq"], 3),
            "baseline_kind": kind, "source": cur["source"], "zone_id": dev["zone_id"],
            "note": f"{cf['dom_freq']:.2f} Hz vs baseline {bf['dom_freq']:.2f} Hz ({cmp['freq_shift_pct']:+.1f}%)"}


def _feat(row):
    return {"rms": row["rms"], "peak": row["peak"], "crest": row["crest"], "kurtosis": row["kurtosis"],
            "dom_freq": row["dom_freq"], "centroid": row["centroid"], "damping": row["damping"]}


# ------------------------------------------------------------------ main computation
def compute(structure_id, at_ms=None, persist=True, force_persist=False):
    s = db.one("SELECT * FROM structures WHERE id=?", (structure_id,))
    if not s:
        raise KeyError(structure_id)
    at = at_ms or db.now_ms()
    mode = s["data_mode"]
    src = _src_sql(mode)
    lim = limits_of(s)
    devs = db.q("SELECT * FROM devices WHERE structure_id=?", (structure_id,))
    zones = db.q("SELECT * FROM zones WHERE structure_id=? ORDER BY idx", (structure_id,))
    items, metrics = [], {"vibration": [], "cracks": [], "strain": [], "deflection": [], "moisture": [], "wim": [],
                          "temperature": [], "rf": []}
    detail = {k: [] for k in WEIGHTS}
    mix = {"sim": 0, "live": 0, "file": 0}

    W20, W1H, W6H = 20 * 60_000, 60 * 60_000, 6 * 3600_000

    def scalar(dev, start, limit=None):
        sql = f"SELECT ts_ms,value,source FROM readings WHERE device_id=? AND ts_ms>? AND ts_ms<=? AND source IN {src} ORDER BY ts_ms DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return db.q(sql, (dev["id"], start, at))

    for d in devs:
        if d["kind"] in ("piezo", "accelerometer", "microphone"):
            r = vibration_for_device(d, at, mode)
            if r:
                metrics["vibration"].append(r)
                if r.get("score") is not None:
                    items.append({"comp": "vibration", "zone": d["zone_id"], "score": r["score"],
                                  "label": f"{d['name']}: {r['note']}", "source": r["source"]})
                mix[r["source"]] += 1
        elif d["kind"] == "strain":
            rows = scalar(d, at - W6H, 3000)
            if rows:
                rows.reverse()
                vals = [x["value"] for x in rows]
                for x in rows:
                    mix[x["source"]] += 1
                recent = [x["value"] for x in rows if x["ts_ms"] > at - W1H]
                peak = max((abs(v) for v in recent), default=0.0)
                ratio = peak / lim["strain_limit_ue"]
                s_peak = 100 - _clamp((ratio - 0.5) / 0.7) * 100
                Dm, cyc = ml.miner_damage(vals)
                life_pct_yr = None
                s_fat = 100.0
                if cyc >= 10:
                    life_pct_yr = Dm / cyc * lim["cycles_per_day"] * 365 * 100
                    s_fat = 100 - _clamp((life_pct_yr - 1.0) / 4.0) * 100
                sc = 0.6 * s_peak + 0.4 * s_fat
                metrics["strain"].append({"device_id": d["id"], "peak_ue": round(peak, 1), "ratio": round(ratio, 3),
                                          "life_pct_per_year": None if life_pct_yr is None else round(life_pct_yr, 3),
                                          "cycles_counted": cyc, "zone_id": d["zone_id"]})
                items.append({"comp": "strain_fatigue", "zone": d["zone_id"], "score": round(sc, 1),
                              "label": f"{d['name']}: peak {peak:.0f} µε ({ratio*100:.0f}% of limit)"
                                       + (f", fatigue {life_pct_yr:.2f}%/yr" if life_pct_yr is not None else ""),
                              "source": rows[-1]["source"]})
        elif d["kind"] == "lvdt":
            rows = scalar(d, at - W1H)
            if rows:
                for x in rows:
                    mix[x["source"]] += 1
                peak = max(abs(x["value"]) for x in rows)
                allow = (s["span_m"] or 10) * 1000 / lim["deflection_ratio"]
                ratio = peak / allow
                sc = 100 - _clamp((ratio - 0.4) / 0.8) * 100
                metrics["deflection"].append({"device_id": d["id"], "peak_mm": round(peak, 2), "allow_mm": round(allow, 1),
                                              "ratio": round(ratio, 3), "zone_id": d["zone_id"]})
                items.append({"comp": "deflection", "zone": d["zone_id"], "score": round(sc, 1),
                              "label": f"{d['name']}: {peak:.1f} mm of {allow:.0f} mm allowable", "source": rows[0]["source"]})
        elif d["kind"] == "moisture":
            rows = scalar(d, at - W20)
            if rows:
                for x in rows:
                    mix[x["source"]] += 1
                m = statistics.fmean(x["value"] for x in rows)
                sc = interp(m, [(4, 100), (8, 70), (12, 35), (16, 5)])
                metrics["moisture"].append({"device_id": d["id"], "pct": round(m, 2), "zone_id": d["zone_id"]})
                items.append({"comp": "environment", "zone": d["zone_id"], "score": round(sc, 1),
                              "label": f"{d['name']}: {m:.1f}% moisture", "source": rows[0]["source"]})
        elif d["kind"] == "wim":
            rows = scalar(d, at - W1H)
            if rows:
                for x in rows:
                    mix[x["source"]] += 1
                vals = [x["value"] for x in rows]
                peak = max(vals)
                n_over = sum(1 for v in vals if v > lim["wim_limit_kn"])
                metrics["wim"].append({"device_id": d["id"], "peak_kn": round(peak, 1), "limit_kn": lim["wim_limit_kn"], "n": len(rows),
                                       "n_over": n_over, "zone_id": d["zone_id"]})
                s_peak = interp(peak / lim["wim_limit_kn"], [(0.6, 100), (1.0, 50), (1.3, 5)])
                s_over = 100 - _clamp((n_over / len(rows)) / 0.05) * 100
                items.append({"comp": "load", "zone": d["zone_id"], "score": round(0.6 * s_peak + 0.4 * s_over, 1),
                              "label": f"{d['name']}: heaviest {peak:.0f} kN of {lim['wim_limit_kn']} kN limit, {n_over} of {len(rows)} vehicles over",
                              "source": rows[0]["source"]})
        elif d["kind"] == "temperature":
            rows = scalar(d, at - 24 * 3600_000)
            if rows:
                for x in rows[:50]:
                    mix[x["source"]] += 1
                vals = [x["value"] for x in rows]
                rng_c, tmax = max(vals) - min(vals), max(vals)
                sc = 0.6 * interp(rng_c, [(10, 100), (20, 80), (30, 45), (40, 10)]) + 0.4 * interp(tmax, [(40, 100), (50, 50), (60, 10)])
                metrics["temperature"].append({"device_id": d["id"], "now_c": round(vals[0], 1), "range_c": round(rng_c, 1), "max_c": round(tmax, 1),
                                               "zone_id": d["zone_id"]})
                items.append({"comp": "thermal", "zone": d["zone_id"], "score": round(sc, 1),
                              "label": f"{d['name']}: {vals[0]:.1f} °C now, 24 h range {rng_c:.1f} °C, peak {tmax:.1f} °C", "source": rows[0]["source"]})
        elif d["kind"] == "rf_coil":
            rows = scalar(d, at - W20)
            if rows:
                for x in rows:
                    mix[x["source"]] += 1
                f = statistics.fmean(x["value"] for x in rows)
                cfg = json.loads(d["config_json"] or "{}")
                f0 = cfg.get("f0")
                if not f0:
                    first = db.q(f"SELECT value FROM readings WHERE device_id=? AND source IN {src} ORDER BY ts_ms LIMIT 10", (d["id"],))
                    f0 = statistics.fmean(r["value"] for r in first) if first else f
                delta = (f - f0) / f0 * 100.0
                sc = interp(abs(delta), [(0.3, 100), (1.0, 85), (2.5, 55), (5.0, 15), (8.0, 0)])
                metrics["rf"].append({"device_id": d["id"], "freq_khz": round(f, 2), "f0_khz": round(f0, 2), "delta_pct": round(delta, 2),
                                      "zone_id": d["zone_id"]})
                items.append({"comp": "internal", "zone": d["zone_id"], "score": round(sc, 1),
                              "label": f"{d['name']}: resonance {delta:+.2f}% from baseline (experimental)", "source": rows[0]["source"]})

    # impact trials (the real rig workflow): latest trial vs the saved baseline feeds the vibration component
    metrics["impact"] = []
    tsrc = {"sim": ("sim",), "live": ("live", "mixed"), "all": ("sim", "live", "mixed")}[mode]
    tr = impact.latest_trial(structure_id, at, tsrc)
    if tr and tr["health_score"] is not None:
        metrics["impact"].append({"trial_id": tr["id"], "condition": tr["condition"], "status": tr["status"],
                                  "combined_score": tr["anomaly_score"], "health_score": tr["health_score"],
                                  "ts_ms": tr["ts_ms"], "source": tr["source"]})
        items.append({"comp": "vibration", "zone": None, "score": round(tr["health_score"], 1),
                      "label": f"Impact trial ({tr['condition']}): {tr['anomaly_score']:.1f}% deviation from baseline - {tr['status']}",
                      "source": "live" if tr["source"] == "mixed" else tr["source"]})
        mix[("live" if tr["source"] == "mixed" else tr["source"])] += 1

    # cracks: latest analysis per zone
    since = at - 180 * 86400_000
    latest = {}
    for c in db.q("SELECT * FROM crack_analyses WHERE structure_id=? AND ts_ms<=? AND ts_ms>? ORDER BY ts_ms",
                  (structure_id, at, since)):
        is_sample = c["origin"] == "sample"  # bundled synthetic images count as simulated, uploads as real files
        if (mode == "live" and is_sample) or (mode == "sim" and not is_sample):
            continue
        latest[c["zone_id"] or "_"] = c
    for zid, c in latest.items():
        if c["scale_px_per_mm"] and c["max_width_mm"] is not None:
            sc = interp(c["max_width_mm"] if c["crack_detected"] else 0, [(0, 100), (0.1, 95), (0.3, 75), (1.0, 40), (3.0, 5)])
            lab = f"Zone image: max width {c['max_width_mm']:.2f} mm" if c["crack_detected"] else "Zone image: no crack found"
        else:
            sc = interp(c["crack_area_pct"] if c["crack_detected"] else 0, [(0, 100), (0.2, 90), (1, 70), (3, 40), (8, 10)])
            lab = f"Zone image (uncalibrated): crack area {c['crack_area_pct']:.2f}%"
        metrics["cracks"].append({"analysis_id": c["id"], "zone_id": c["zone_id"], "max_width_mm": c["max_width_mm"],
                                  "area_pct": c["crack_area_pct"], "severity": c["severity"], "detected": bool(c["crack_detected"]),
                                  "calibrated": bool(c["scale_px_per_mm"]), "ts_ms": c["ts_ms"]})
        items.append({"comp": "cracks", "zone": c["zone_id"], "score": round(sc, 1), "label": lab, "source": "sim" if is_sample else "file"})

    # aggregate to structure-level components. A channel an engineer switched off is shown but not used.
    disabled = set(db.get_setting(f"channels.disabled.{structure_id}", []) or [])
    comps, comp_detail = {}, {}
    for k in WEIGHTS:
        its = [i for i in items if i["comp"] == k]
        comps[k] = round(_agg([i["score"] for i in its]), 1) if its else None
        comp_detail[k] = {"score": comps[k], "weight": WEIGHTS[k], "available": bool(its), "disabled": k in disabled,
                          "items": [{"label": i["label"], "score": i["score"], "zone": i["zone"]} for i in its]}
    shown_items = items
    items = [i for i in items if i["comp"] not in disabled]
    comps = {k: (None if k in disabled else v) for k, v in comps.items()}
    score, coverage = combine(comps)

    # per-zone scores for the heatmap (vibration is a global property: used at half weight outside its own zone)
    zone_out = {}
    for z in zones:
        zc = {}
        for k in WEIGHTS:
            own = [i["score"] for i in items if i["comp"] == k and i["zone"] == z["id"]]
            if own:
                zc[k] = _agg(own)
            elif k == "vibration":
                g = [i["score"] for i in items if i["comp"] == "vibration"]
                zc[k] = _agg(g) if g else None
            else:
                zc[k] = None
        sc, cov = combine(zc)
        has_local = any(i["zone"] == z["id"] for i in items)
        zone_out[z["id"]] = {"score": None if sc is None else round(sc, 1), "band": band(sc), "coverage": round(cov, 2),
                             "local_data": has_local}

    est = None
    try:
        est = round(ml.forest_estimate(comps), 1) if score is not None else None
    except Exception:
        est = None

    drivers = []
    for k, v in sorted(((k, v) for k, v in comps.items() if v is not None), key=lambda kv: (100 - kv[1]) * WEIGHTS[kv[0]], reverse=True):
        if v < 90:
            worst = min((i for i in items if i["comp"] == k), key=lambda i: i["score"])
            drivers.append({"component": k, "label": LABELS[k], "score": v, "reason": worst["label"]})

    result = {"structure_id": structure_id, "ts_ms": at, "score": None if score is None else round(score, 1),
              "band": band(score), "coverage": round(coverage, 2), "components": comp_detail, "zones": zone_out,
              "drivers": drivers[:3], "metrics": metrics, "source_mix": mix, "data_mode": mode,
              "method": METHOD, "forest_estimate": est}
    if persist and score is not None:
        last = db.one("SELECT ts_ms FROM health_scores WHERE structure_id=? ORDER BY ts_ms DESC LIMIT 1", (structure_id,))
        if force_persist or at_ms or not last or at - last["ts_ms"] >= 60_000:
            hid = db.uid()
            db.insert("health_scores", {"id": hid, "structure_id": structure_id, "ts_ms": at, "score": result["score"],
                                        "band": result["band"], "coverage": result["coverage"],
                                        "components_json": json.dumps(comp_detail), "zones_json": json.dumps(zone_out),
                                        "method": METHOD, "data_mode": mode})
            from . import cloud_sync
            cloud_sync.enqueue("health_scores", hid)
            result["id"] = hid
    return result


def latest(structure_id):
    r = db.one("SELECT * FROM health_scores WHERE structure_id=? ORDER BY ts_ms DESC LIMIT 1", (structure_id,))
    if not r:
        return None
    return {"id": r["id"], "ts_ms": r["ts_ms"], "score": r["score"], "band": r["band"], "coverage": r["coverage"],
            "components": json.loads(r["components_json"]), "zones": json.loads(r["zones_json"] or "{}"),
            "method": r["method"], "data_mode": r["data_mode"]}
