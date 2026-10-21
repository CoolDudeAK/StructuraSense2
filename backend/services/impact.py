"""Impact Lab - the real rig workflow from the team's Streamlit prototype, ported to the platform.

Hardware: Arduino UNO + 3 piezo sensors on a concrete specimen. The firmware prints one line every ~100 ms:
    184,126,171          or          S1:184,S2:126,S3:171
(peak-to-peak ADC counts per sensor over a 100 ms window).

Workflow (unchanged from the original prototype):
  1. Baseline calibration: record ~20 impact trials on the INTACT specimen; per sensor, one trial value =
     max - min of the P2P stream during the trial. Baseline = mean/std of those values.
  2. Trials: record a trial (Intact or Damaged) -> compare with baseline.
  3. deviation_i (%)  = |current_i - baseline_mean_i| / baseline_mean_i * 100
     combined score   = mean of the three deviations
     prototype health = max(0, 100 - combined score)
     <= anomaly threshold (20%) NORMAL | <= urgent threshold (60%) POSSIBLE ANOMALY | above URGENT REVIEW
Thresholds are experimental starting values, NOT validated engineering limits.

Implementation note: the live status here compares a ROLLING WINDOW (same length as a trial) against the baseline,
because a single 100 ms reading and a trial value are different quantities. The original Dashboard compared a
single reading against the trial baseline.
"""
import csv
import io
import json
import math
import re
import threading
import time

import numpy as np

from .. import config, db

STATUS_NORMAL, STATUS_ANOMALY, STATUS_URGENT = "NORMAL", "POSSIBLE ANOMALY", "URGENT REVIEW"
DEFAULTS = {"trial_duration_sec": 5, "sampling_interval_sec": 0.1, "num_baseline_trials": 20,
            "anomaly_threshold_pct": 20.0, "urgent_threshold_pct": 60.0, "min_quality_samples": 5, "baud_rate": 115200}
MIN_VALID, MAX_VALID = 0.0, 5000.0
LABELS = {"live": "LIVE HARDWARE DATA", "sim": "DEMO/SIMULATION DATA", "mixed": "MIXED (LIVE + DEMO)"}
_jobs = {}
_jobs_lock = threading.Lock()


# ------------------------------------------------------------------ ported maths (same formulas as the prototype)
def p2p(v):
    return float(max(v) - min(v)) if len(v) else 0.0


def mean(v):
    return float(sum(v) / len(v)) if len(v) else 0.0


def std(v):  # population standard deviation, as in the prototype
    if len(v) < 2:
        return 0.0
    m = mean(v)
    return float(math.sqrt(sum((x - m) ** 2 for x in v) / len(v)))


def deviation(cur, base):
    if base is None or base == 0:
        return 0.0
    return float(abs(cur - base) / base * 100.0)


def summarize(s1, s2, s3):
    return {f"sensor{i}": {"peak_to_peak": p2p(v), "mean": mean(v), "std": std(v), "max": max(v) if v else 0.0,
                           "min": min(v) if v else 0.0} for i, v in enumerate((s1, s2, s3), 1)}


def calc_baseline(trials):
    out = {}
    for i in (1, 2, 3):
        vals = [t[f"s{i}"] for t in trials]
        out[f"s{i}_mean"], out[f"s{i}_std"] = mean(vals), std(vals)
    return out


def anomaly(cur: dict, base: dict):
    devs = {f"sensor{i}": deviation(cur[f"sensor{i}"], base[f"s{i}_mean"]) for i in (1, 2, 3)}
    combined = sum(devs.values()) / 3.0
    return {"deviations": devs, "combined_score": combined, "health_score": max(0.0, 100.0 - combined),
            "largest_deviation_sensor": max(devs, key=devs.get)}


def classify(score, thr, urgent):
    if score <= thr:
        return STATUS_NORMAL
    if urgent is not None and score > urgent:
        return STATUS_URGENT
    return STATUS_ANOMALY


# ------------------------------------------------------------------ packet parsing (their formats)
def parse_packet(line):
    """'184,126,171' or 'S1:184,S2:126,S3:171' -> (s1,s2,s3). Raises ValueError with a readable reason."""
    if line is None or not str(line).strip():
        raise ValueError("Empty packet.")
    line = str(line).strip()
    if "S1" in line.upper() or ":" in line:
        found = {}
        for idx, val in re.findall(r"[Ss]\s*([123])\s*:\s*(-?\d+\.?\d*)", line):
            found[int(idx)] = float(val)
        if len(found) != 3:
            raise ValueError(f"Could not read all three sensors from '{line}'.")
        vals = [found[1], found[2], found[3]]
    else:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            raise ValueError(f"Expected 3 comma-separated values, got {len(parts)}: '{line}'.")
        try:
            vals = [float(p) for p in parts]
        except ValueError:
            raise ValueError(f"Non-numeric value in '{line}'.")
    for v in vals:
        if v != v or v < MIN_VALID or v > MAX_VALID:
            raise ValueError(f"Value {v} is outside the plausible sensor range ({MIN_VALID:.0f}-{MAX_VALID:.0f}).")
    return tuple(vals)


# ------------------------------------------------------------------ structure helpers
def devices(sid):
    out = []
    for d in db.q("SELECT * FROM devices WHERE structure_id=? AND kind='piezo'", (sid,)):
        cfg = json.loads(d["config_json"] or "{}")
        if cfg.get("mode") == "p2p":
            out.append((int(cfg.get("sensor", 0)), d))
    out.sort(key=lambda t: t[0])
    return [d for _, d in out]


def supports(sid):
    return len(devices(sid)) == 3


def get_settings(sid):
    s = dict(DEFAULTS)
    s.update(db.get_setting(f"impact.settings.{sid}", {}) or {})
    return s


def put_settings(sid, d):
    cur = get_settings(sid)
    rules = {"trial_duration_sec": (1, 60, int), "sampling_interval_sec": (0.01, 2.0, float),
             "num_baseline_trials": (3, 100, int), "anomaly_threshold_pct": (1.0, 100.0, float),
             "urgent_threshold_pct": (1.0, 200.0, float), "min_quality_samples": (1, 100, int),
             "baud_rate": (300, 250000, int)}
    for k, (lo, hi, typ) in rules.items():
        if k in d:
            v = typ(d[k])
            if v < lo or v > hi:
                raise ValueError(f"{k} must be between {lo} and {hi}.")
            cur[k] = v
    if cur["urgent_threshold_pct"] <= cur["anomaly_threshold_pct"]:
        raise ValueError("The urgent threshold must be greater than the anomaly threshold.")
    db.set_setting(f"impact.settings.{sid}", cur)
    return cur


def baseline(sid):
    return db.one("SELECT * FROM impact_baselines WHERE structure_id=?", (sid,))


def baseline_valid(b):
    return bool(b) and (b.get("num_trials") or 0) > 0 and all(b.get(f"s{i}_mean") for i in (1, 2, 3))


def _base_dict(b):
    return {f"s{i}_mean": b[f"s{i}_mean"] for i in (1, 2, 3)}


# ------------------------------------------------------------------ writing packets (hardware or sim)
def write_packet(sid, vals, ts_ms, source):
    devs = devices(sid)
    if len(devs) != 3:
        raise ValueError("This structure has no 3-channel piezo setup.")
    db.run_many("INSERT INTO readings(device_id,ts_ms,value,source,batch_id) VALUES(?,?,?,?,NULL)",
                [(d["id"], ts_ms, float(v), source) for d, v in zip(devs, vals)])


# ------------------------------------------------------------------ reading windows
def window(sid, t0, t1, prefer=None):
    """Aligned (ts, s1,s2,s3, source) rows between t0 and t1. Uses live rows if any exist, else demo rows."""
    devs = devices(sid)
    if len(devs) != 3:
        return [], "sim"
    ids = [d["id"] for d in devs]
    rows = db.q(f"SELECT device_id,ts_ms,value,source FROM readings WHERE device_id IN ({','.join('?'*3)}) "
                "AND ts_ms>=? AND ts_ms<=? ORDER BY ts_ms", ids + [t0, t1])
    by = {}
    for r in rows:
        by.setdefault((r["ts_ms"], r["source"]), {})[r["device_id"]] = r["value"]
    live = [(ts, [v[i] for i in ids]) for (ts, src), v in sorted(by.items()) if src in ("live", "file") and len(v) == 3]
    sim = [(ts, [v[i] for i in ids]) for (ts, src), v in sorted(by.items()) if src == "sim" and len(v) == 3]
    if prefer == "sim":
        use, src = sim, "sim"
    elif live:
        use, src = live, "live"
        if sim:
            src = "mixed" if len(sim) > len(live) * 0.25 else "live"
    else:
        use, src = sim, "sim"
    return use, src


# ------------------------------------------------------------------ recording (start / finish)
def start_job(sid, purpose, condition, duration):
    jid = db.uid()
    with _jobs_lock:
        for k in [k for k, v in _jobs.items() if time.time() - v["t0"] > 900]:
            _jobs.pop(k, None)
        _jobs[jid] = {"sid": sid, "purpose": purpose, "condition": condition, "duration": duration,
                      "t0": time.time(), "t0_ms": db.now_ms()}
    return {"job_id": jid, "duration_s": duration, "started_ms": _jobs[jid]["t0_ms"]}


def finish_job(jid, user=None):
    with _jobs_lock:
        job = _jobs.pop(jid, None)
    if not job:
        raise ValueError("This recording has expired. Start it again.")
    elapsed = time.time() - job["t0"]
    if elapsed < job["duration"] - 0.6:
        with _jobs_lock:
            _jobs[jid] = job
        raise ValueError(f"The recording is still running ({elapsed:.1f} of {job['duration']} s).")
    sid = job["sid"]
    st = get_settings(sid)
    rows, source = window(sid, job["t0_ms"], db.now_ms())
    if len(rows) < st["min_quality_samples"]:
        raise ValueError(f"Only {len(rows)} readings arrived (need {st['min_quality_samples']}). "
                         "Check the Arduino connection or switch on the demo stream, then record again.")
    cols = [[r[1][i] for r in rows] for i in range(3)]
    summ = summarize(*cols)
    cur = {f"sensor{i}": summ[f"sensor{i}"]["peak_to_peak"] for i in (1, 2, 3)}
    now = db.now_ms()
    if job["purpose"] == "calibration":
        db.insert("impact_calibration", {"id": db.uid(), "structure_id": sid, "ts_ms": now, "s1": cur["sensor1"],
                                         "s2": cur["sensor2"], "s3": cur["sensor3"], "source": source})
        return {"purpose": "calibration", "values": cur, "samples": len(rows), "source": source,
                "calibration": calibration_state(sid)}
    mean_resp = mean([summ[f"sensor{i}"]["mean"] for i in (1, 2, 3)])
    max_resp = max(summ[f"sensor{i}"]["max"] for i in (1, 2, 3))
    min_resp = min(summ[f"sensor{i}"]["min"] for i in (1, 2, 3))
    trial = save_trial(sid, job["condition"], cur, mean_resp, max_resp, min_resp, source, len(rows), job["duration"],
                       trace=[[r[0] for r in rows], *cols], ts_ms=now, st=st)
    return {"purpose": "trial", "trial": trial, "samples": len(rows)}


def save_trial(sid, condition, cur, mean_resp, max_resp, min_resp, source, samples, duration, trace=None, ts_ms=None,
               st=None, notes=""):
    st = st or get_settings(sid)
    b = baseline(sid)
    score = hs = None
    status = "NO BASELINE"
    devs = None
    if baseline_valid(b):
        res = anomaly(cur, _base_dict(b))
        score, hs, devs = res["combined_score"], res["health_score"], res["deviations"]
        status = classify(score, st["anomaly_threshold_pct"], st["urgent_threshold_pct"])
    tr = None
    if trace:
        ts, a, b2, c = trace
        step = max(1, len(ts) // 300)
        t0 = ts[0]
        tr = json.dumps({"t": [round((x - t0) / 1000, 2) for x in ts[::step]], "s1": [round(x, 1) for x in a[::step]],
                         "s2": [round(x, 1) for x in b2[::step]], "s3": [round(x, 1) for x in c[::step]]})
    tid = db.uid()
    db.insert("impact_trials", {"id": tid, "structure_id": sid, "ts_ms": ts_ms or db.now_ms(), "condition": condition,
                                "s1": cur["sensor1"], "s2": cur["sensor2"], "s3": cur["sensor3"],
                                "mean_response": mean_resp, "max_response": max_resp, "min_response": min_resp,
                                "anomaly_score": score, "health_score": hs, "status": status, "source": source,
                                "samples": samples, "duration_s": duration, "trace_json": tr, "notes": notes})
    out = trial_out(db.one("SELECT * FROM impact_trials WHERE id=?", (tid,)), with_trace=True)
    out["deviations"] = devs
    return out


def trial_out(r, with_trace=False):
    if not r:
        return None
    o = {k: r[k] for k in r if k != "trace_json"}
    o["data_source"] = LABELS.get(r["source"], r["source"])
    if with_trace and r.get("trace_json"):
        o["trace"] = json.loads(r["trace_json"])
    return o


# ------------------------------------------------------------------ calibration
def calibration_state(sid):
    rows = db.q("SELECT * FROM impact_calibration WHERE structure_id=? ORDER BY ts_ms", (sid,))
    preview = None
    if rows:
        preview = calc_baseline(rows)
    srcs = {r["source"] for r in rows}
    return {"trials": rows, "count": len(rows), "target": get_settings(sid)["num_baseline_trials"], "preview": preview,
            "source": (srcs.pop() if len(srcs) == 1 else ("mixed" if srcs else None))}


def undo_calibration(sid):
    r = db.one("SELECT id FROM impact_calibration WHERE structure_id=? ORDER BY ts_ms DESC LIMIT 1", (sid,))
    if r:
        db.run("DELETE FROM impact_calibration WHERE id=?", (r["id"],))


def clear_calibration(sid):
    db.run("DELETE FROM impact_calibration WHERE structure_id=?", (sid,))


def save_baseline(sid, specimen_id="specimen-1"):
    st = calibration_state(sid)
    if st["count"] < 3:
        raise ValueError("Record at least 3 intact trials before saving a baseline.")
    b = calc_baseline(st["trials"])
    row = {"structure_id": sid, **b, "num_trials": st["count"], "specimen_id": specimen_id, "created_ms": db.now_ms(),
           "source": st["source"] or "sim"}
    db.run("DELETE FROM impact_baselines WHERE structure_id=?", (sid,))
    db.insert("impact_baselines", row)
    clear_calibration(sid)
    return row


# ------------------------------------------------------------------ live status (rolling window)
def live(sid, window_n=100):
    st = get_settings(sid)
    now = db.now_ms()
    rows, source = window(sid, now - 120_000, now)
    rows = rows[-max(5, min(int(window_n), 600)):]
    out = {"points": {"t": [r[0] for r in rows], "s1": [r[1][0] for r in rows], "s2": [r[1][1] for r in rows],
                      "s3": [r[1][2] for r in rows]},
           "source": source if rows else None, "data_source": LABELS.get(source) if rows else None,
           "latest": None, "connected": bool(rows) and now - rows[-1][0] < 3000}
    if rows:
        out["latest"] = {"ts_ms": rows[-1][0], "s1": rows[-1][1][0], "s2": rows[-1][1][1], "s3": rows[-1][1][2]}
    b = baseline(sid)
    out["baseline"] = b
    out["status"] = None
    if rows and baseline_valid(b):
        recent = [r for r in rows if r[0] >= now - st["trial_duration_sec"] * 1000]
        if len(recent) >= st["min_quality_samples"]:
            cur = {f"sensor{i}": p2p([r[1][i - 1] for r in recent]) for i in (1, 2, 3)}
            res = anomaly(cur, _base_dict(b))
            out["status"] = {**res, "current_p2p": cur, "window_s": st["trial_duration_sec"],
                             "status": classify(res["combined_score"], st["anomaly_threshold_pct"], st["urgent_threshold_pct"])}
    return out


# ------------------------------------------------------------------ history / analysis / export
def trials(sid, condition=None, status=None, limit=500):
    sql, args = "SELECT * FROM impact_trials WHERE structure_id=?", [sid]
    if condition and condition != "All":
        sql += " AND condition=?"
        args.append(condition)
    if status and status != "All":
        sql += " AND status=?"
        args.append(status)
    sql += " ORDER BY ts_ms DESC LIMIT ?"
    args.append(limit)
    return [trial_out(r) for r in db.q(sql, args)]


def analysis(sid):
    rows = db.q("SELECT * FROM impact_trials WHERE structure_id=? ORDER BY ts_ms", (sid,))
    intact = [r for r in rows if r["condition"] == "Intact"]
    damaged = [r for r in rows if r["condition"] == "Damaged"]

    def stats(sub):
        out = []
        for i in (1, 2, 3):
            v = [r[f"s{i}"] for r in sub if r[f"s{i}"] is not None]
            sd = float(np.std(v, ddof=1)) if len(v) > 1 else None  # pandas .std() = sample std
            out.append({"sensor": i, "mean": round(mean(v), 2) if v else None, "std": None if sd is None else round(sd, 2), "trials": len(v)})
        return out

    si, sd_ = stats(intact), stats(damaged)
    dev = []
    if intact and damaged:
        for a, b in zip(si, sd_):
            pct = abs(b["mean"] - a["mean"]) / a["mean"] * 100 if a["mean"] else None
            dev.append({"sensor": a["sensor"], "intact_mean": a["mean"], "damaged_mean": b["mean"],
                        "pct_deviation": None if pct is None else round(pct, 1), "intact_std": a["std"], "damaged_std": b["std"]})
    return {"intact": si, "damaged": sd_, "n_intact": len(intact), "n_damaged": len(damaged), "deviation": dev,
            "scores": [{"id": r["id"], "ts_ms": r["ts_ms"], "condition": r["condition"], "score": r["anomaly_score"],
                        "status": r["status"]} for r in rows if r["anomaly_score"] is not None],
            "per_trial": [{"ts_ms": r["ts_ms"], "condition": r["condition"], "s1": r["s1"], "s2": r["s2"], "s3": r["s3"]} for r in rows]}


def export_csv(sid):
    fields = ["id", "timestamp", "condition", "sensor1", "sensor2", "sensor3", "mean_response", "max_response",
              "min_response", "anomaly_score", "status", "data_source", "notes"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for i, r in enumerate(reversed(db.q("SELECT * FROM impact_trials WHERE structure_id=? ORDER BY ts_ms", (sid,))), 1):
        w.writerow({"id": r["id"], "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(r["ts_ms"] / 1000)),
                    "condition": r["condition"], "sensor1": r["s1"], "sensor2": r["s2"], "sensor3": r["s3"],
                    "mean_response": r["mean_response"], "max_response": r["max_response"], "min_response": r["min_response"],
                    "anomaly_score": r["anomaly_score"], "status": r["status"], "data_source": LABELS.get(r["source"]),
                    "notes": r["notes"] or ""})
    return buf.getvalue()


def latest_trial(sid, at_ms, sources):
    return db.one(f"SELECT * FROM impact_trials WHERE structure_id=? AND ts_ms<=? AND source IN ({','.join('?' for _ in sources)}) "
                  "ORDER BY ts_ms DESC LIMIT 1", [sid, at_ms, *sources])


# ------------------------------------------------------------------ simulated tap stream (DEMO data)
TAP_DECAY = [1.0, 0.55, 0.25, 0.10]
QUIET = (18.0, 3.0)
BASE_AMP = {1: 180.0, 2: 165.0, 3: 174.0}
# Demo scenarios. The original prototype's 'anomaly' (S1 +5 %, S2 -30 %, S3 +10 %) only produces ~15 % combined
# deviation, which is BELOW its own 20 % threshold, so 'anomaly' here is stronger and 'severe' is added.
GAINS = {
    "normal": {1: (1.0, 1.0), 2: (1.0, 1.0), 3: (1.0, 1.0)},
    "anomaly": {1: (1.10, 1.0), 2: (0.45, 2.0), 3: (1.20, 1.0)},    # ~28 % -> POSSIBLE ANOMALY
    "severe": {1: (1.60, 1.5), 2: (0.06, 2.0), 3: (1.90, 1.5)},     # ~80 % -> URGENT REVIEW
}
SCENARIOS = {"normal": "Normal response (like the intact specimen)",
             "anomaly": "Possible anomaly (S2 response drops, S1/S3 rise)",
             "severe": "Severe change (strong shift on all sensors)"}


class TapSim:
    """Produces 100 ms packets that look like repeated impacts on the specimen (quiet noise + decaying spikes)."""

    def __init__(self, scenario="normal", rng=None):
        self.scenario = scenario
        self.rng = rng or np.random.default_rng()
        self.next_gap = 0
        self.decay_idx = None
        self.amp = {}

    def packet(self):
        r = self.rng
        if self.decay_idx is None:
            if self.next_gap <= 0:
                self.decay_idx = 0
                self.next_gap = int(r.integers(15, 31))  # 1.5 - 3 s between taps at 10 packets/s
                self.amp = {}
                for i in (1, 2, 3):
                    g, sg = GAINS.get(self.scenario, GAINS["normal"])[i]
                    self.amp[i] = BASE_AMP[i] * g * (1 + r.normal(0, 0.035 * sg))
            else:
                self.next_gap -= 1
        vals = []
        for i in (1, 2, 3):
            q = max(0.0, r.normal(*QUIET))
            if self.decay_idx is not None:
                q = max(q, self.amp[i] * TAP_DECAY[self.decay_idx] + r.normal(0, 2.0))
            vals.append(round(max(0.0, q), 1))
        if self.decay_idx is not None:
            self.decay_idx += 1
            if self.decay_idx >= len(TAP_DECAY):
                self.decay_idx = None
            self.next_gap -= 1
        return vals


def simulate_trial_values(scenario, rng, duration=5.0, hz=10):
    sim = TapSim(scenario, rng)
    n = int(duration * hz)
    pk = [sim.packet() for _ in range(n)]
    return [[p[i] for p in pk] for i in range(3)]
