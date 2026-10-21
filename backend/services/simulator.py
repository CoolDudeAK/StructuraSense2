"""SIMULATED data generator. Everything it writes is tagged source='sim' so the UI and the health index can
always tell it apart from real hardware ('live') or imported files ('file').

Physics used (simple but real relationships):
  * Vibration: modal superposition of decaying sinusoids excited by random impulses (vehicles / a tap on a
    specimen). Damage lowers stiffness, so natural frequency f = f0*(1 - 0.18*damage) and damping rises.
    A small temperature effect on frequency (-0.04 %/degC) is included.
  * Vehicles: a shared vehicle event (weight in kN) drives the strain gauges, the LVDT and the WIM sensor together,
    so strain-vs-weight regression and the overload rule see consistent data.
"""
import json
import math
import threading
import time

import numpy as np

from .. import config, db, events
from . import alerts_engine, cloud_sync, dsp, health, impact

WAVE_PROFILES = {
    "specimen": dict(fs=2000, n=1024, f0=240.0, zeta0=0.012, modes=((1, 1.0), (2.7, 0.5), (5.1, 0.25)),
                     events=(1, 1), ev_rate=None, noise=0.03, amp=300.0, unit="mV", every_s=30),
    "bridge": dict(fs=100, n=2048, f0=4.8, zeta0=0.02, modes=((1, 1.0), (2.4, 0.5), (3.9, 0.3)),
                   events=None, ev_rate=0.35, noise=0.10, amp=0.02, unit="g", every_s=120),
    "flyover": dict(fs=100, n=2048, f0=3.1, zeta0=0.025, modes=((1, 1.0), (2.2, 0.45), (3.6, 0.25)),
                    events=None, ev_rate=0.30, noise=0.10, amp=0.02, unit="g", every_s=120),
}

SCENARIOS = {
    "healthy": "Healthy - no change",
    "gradual_degradation": "Gradual stiffness loss (hours)",
    "crack_initiation": "Crack initiation (fast, seconds to minutes)",
    "moisture_ingress": "Moisture ingress",
}

_state = {"running": False, "interval": config.SIM_INTERVAL_S, "ticks": 0, "last_tick_ms": None}
_next_wave = {}
_pending_overload = set()
_last_health = {}
_stop = threading.Event()
_rng = np.random.default_rng()


# ------------------------------------------------------------------ waveform synthesis
def synth_waveform(prof, damage, rng, temp_c=25.0, f0=None):
    fs, n = prof["fs"], prof["n"]
    t = np.arange(n) / fs
    scale = (1 - 0.18 * damage) * (1 - 0.0004 * (temp_c - 25.0))
    zeta = prof["zeta0"] * (1 + 3.0 * damage)
    f0 = f0 or prof["f0"]
    T = n / fs
    if prof.get("events"):
        k = int(rng.integers(prof["events"][0], prof["events"][1] + 1))
        times = [0.03 * T] * k
    else:
        k = max(2, int(rng.poisson(prof["ev_rate"] * T)))
        times = rng.uniform(0, 0.9 * T, k)
    x = np.zeros(n)
    for te in times:
        a = rng.lognormal(0, 0.45)
        tt = t - te
        m = tt >= 0
        for ratio, mamp in prof["modes"]:
            fm = f0 * ratio * scale
            wd = 2 * math.pi * fm * math.sqrt(1 - zeta ** 2)
            x[m] += a * mamp * np.exp(-zeta * 2 * math.pi * fm * tt[m]) * np.sin(wd * tt[m] + rng.uniform(0, 0.4))
    x = x / max(np.std(x), 1e-9) * 0.5
    x += rng.normal(0, prof["noise"], n)
    return x * prof["amp"]


def _profile(dev):
    cfg = json.loads(dev.get("config_json") or "{}")
    prof = dict(WAVE_PROFILES.get(cfg.get("profile", "bridge"), WAVE_PROFILES["bridge"]))
    if dev.get("fs"):
        prof["fs"] = dev["fs"]
    prof["f0"] = cfg.get("f0", prof["f0"])
    return prof, cfg


def capture(dev, damage, ts_ms=None, rng=None, temp_c=25.0, baseline=False, label=None, notes=None, source="sim"):
    """Generate one simulated waveform capture, analyse it, store it. Returns the stored row id."""
    rng = rng or _rng
    prof, cfg = _profile(dev)
    x = synth_waveform(prof, damage, rng, temp_c=temp_c, f0=prof["f0"])
    f = dsp.analyze(x, prof["fs"])
    wid = db.uid()
    db.insert("waveforms", {"id": wid, "device_id": dev["id"], "structure_id": dev["structure_id"],
                            "ts_ms": ts_ms or db.now_ms(), "fs": prof["fs"], "n": len(x), "samples": dsp.pack(x),
                            "source": source, "rms": f["rms"], "peak": f["peak"], "crest": f["crest"], "kurtosis": f["kurtosis"],
                            "dom_freq": f["dom_freq"], "centroid": f["centroid"], "damping": f["damping"],
                            "bands_json": json.dumps(f["bands"]), "is_baseline": 1 if baseline else 0, "label": label,
                            "notes": notes, "sim_damage": damage})
    cloud_sync.enqueue("waveforms", wid)
    return wid


# ------------------------------------------------------------------ scalar physics
def _hour_ist(ts_ms):
    return ((ts_ms / 3600_000.0) + 5.5) % 24


def temperature_c(ts_ms, rng):
    h = _hour_ist(ts_ms)
    return 26 + 8 * math.sin(2 * math.pi * (h - 9) / 24) + rng.normal(0, 0.15)


def traffic_rate(ts_ms):
    h = _hour_ist(ts_ms)
    return 0.01 + 0.09 * max(0.0, math.sin(math.pi * (h - 5) / 16)) if 5 <= h <= 21 else 0.01


def vehicle_weight(rng):
    return float(rng.lognormal(math.log(120), 0.40))


def scalar_value(dev, cfg, st, ts_ms, temp, W, rng):
    k = dev["kind"]
    dmg = st["damage"]
    if k == "temperature":
        return temp
    if k == "strain":
        gain = cfg.get("gain", 0.55)
        base = rng.normal(0, 2.5)
        return base + (gain * W * (1 + dmg * 1.6) if W else 0.0)
    if k == "lvdt":
        c = cfg.get("c", 0.06)
        return rng.normal(0, 0.04) + (c * W * (1 + dmg * 2.5) if W else 0.0)
    if k == "moisture":
        h = _hour_ist(ts_ms)
        return cfg.get("base", 5.5) + st["moisture_boost"] + 0.6 * math.sin(2 * math.pi * (h - 6) / 24) + rng.normal(0, 0.05)
    if k == "wim":
        return W if W else None
    if k == "rf_coil":
        # EXPERIMENTAL: resonant frequency (kHz) of an embedded RF coil; internal voids/cracks detune it slightly.
        f0 = cfg.get("f0", 1000.0)
        return f0 * (1.0 - 0.07 * dmg - 0.0008 * st["moisture_boost"] + rng.normal(0, 0.0004))
    return None


def _state_row(sid):
    r = db.one("SELECT * FROM sim_state WHERE structure_id=?", (sid,))
    if not r:
        db.insert("sim_state", {"structure_id": sid, "scenario": "healthy", "damage": 0.0, "moisture_boost": 0.0,
                                "speed": 0.0, "updated_ms": db.now_ms()})
        r = db.one("SELECT * FROM sim_state WHERE structure_id=?", (sid,))
    return r


def _advance_state(st, dt):
    sc = st["scenario"]
    dmg, mb = st["damage"], st["moisture_boost"]
    if sc == "gradual_degradation":
        dmg = min(0.8, dmg + (st["speed"] or 2e-5) * dt)
    elif sc == "crack_initiation":
        dmg = min(0.8, dmg + 0.008 * dt)
        if dmg >= 0.35:
            sc = "healthy"  # hold the damage, stop growing
    elif sc == "moisture_ingress":
        mb = min(10.0, mb + 0.004 * dt)
    return {"scenario": sc, "damage": dmg, "moisture_boost": mb}


def sim_structures():
    return db.q("SELECT * FROM structures WHERE data_mode IN ('sim','all')")


def tick(sid, ts_ms=None, dt=None, persist_health=True):
    """One simulation step for a structure. Returns number of readings written."""
    now = ts_ms or db.now_ms()
    dt = dt or _state["interval"]
    st = _state_row(sid)
    new = _advance_state(st, dt)
    if new != {k: st[k] for k in new}:
        db.update("sim_state", sid, {**new, "updated_ms": now}, key="structure_id")
    st = {**st, **new}
    rng = _rng
    temp = temperature_c(now, rng)
    W = None
    if sid in _pending_overload:
        _pending_overload.discard(sid)
        W = float(rng.uniform(520, 600))
    elif rng.random() < min(0.9, traffic_rate(now) * dt):
        W = vehicle_weight(rng)
    devs = [d for d in db.q("SELECT * FROM devices WHERE structure_id=? AND source_type='simulated'", (sid,))]
    rows, payload = [], []
    for d in devs:
        if json.loads(d["config_json"] or "{}").get("mode") == "p2p":
            continue  # specimen piezo channels are driven by the 10 Hz demo stream below
        if d["channel"] == "scalar":
            cfg = json.loads(d["config_json"] or "{}")
            v = scalar_value(d, cfg, st, now, temp, W if cfg.get("traffic", True) else None, rng)
            if v is not None:
                rows.append((d["id"], now, float(v), "sim", None))
                payload.append({"device_id": d["id"], "value": round(float(v), 3), "unit": d["unit"], "source": "sim"})
        elif d["channel"] == "waveform":
            prof, _ = _profile(d)
            due = _next_wave.get(d["id"], 0)
            if now >= due:
                _next_wave[d["id"]] = now + prof["every_s"] * 1000
                wid = capture(d, st["damage"], ts_ms=now, rng=rng, temp_c=temp)
                events.publish("waveform", {"structure_id": sid, "device_id": d["id"], "id": wid, "ts_ms": now, "source": "sim"})
    if rows:
        db.run_many("INSERT INTO readings(device_id,ts_ms,value,source,batch_id) VALUES(?,?,?,?,?)", rows)
        db.run(f"UPDATE devices SET last_seen_ms=? WHERE id IN ({','.join('?' for _ in rows)})", [now] + [r[0] for r in rows])
        events.publish("tick", {"structure_id": sid, "ts_ms": now, "readings": payload,
                                "sim": {"scenario": st["scenario"], "damage": round(st["damage"], 3)}})
    if persist_health and now - _last_health.get(sid, 0) >= 10_000:
        _last_health[sid] = now
        refresh_health(sid)
    return len(rows)


def refresh_health(sid, at_ms=None, historic=False, force=False):
    res = health.compute(sid, at_ms=at_ms, persist=True, force_persist=force)
    created = alerts_engine.evaluate(sid, res, historic=historic)
    if not historic:
        events.publish("health", {"structure_id": sid, "score": res["score"], "band": res["band"], "ts_ms": res["ts_ms"],
                                  "new_alerts": len(created)})
    return res


# ------------------------------------------------------------------ history (seed)
def generate_history(sid, hours, step_s=300, damage_start=0.0, damage_end=0.0, moisture_end=0.0,
                     wave_every_s=7200, n_baseline=3, seed=1, health_every_s=3600):
    rng = np.random.default_rng(seed)
    end = db.now_ms()
    start = end - int(hours * 3600_000)
    devs = db.q("SELECT * FROM devices WHERE structure_id=? AND source_type='simulated'", (sid,))
    total = (end - start) / 1000.0
    ts = start
    readings, next_wave, next_health = [], start + wave_every_s * 1000, start + 6 * 3600_000
    baselines_done = False
    while ts <= end:
        frac = (ts - start) / (end - start)
        dmg = damage_start + (damage_end - damage_start) * frac ** 1.3
        mb = moisture_end * frac
        st = {"damage": dmg, "moisture_boost": mb}
        temp = temperature_c(ts, rng)
        W = vehicle_weight(rng) if rng.random() < 0.85 else None
        for d in devs:
            if d["channel"] == "scalar":
                cfg = json.loads(d["config_json"] or "{}")
                v = scalar_value(d, cfg, st, ts, temp, W if cfg.get("traffic", True) else None, rng)
                if v is not None:
                    readings.append((d["id"], ts, float(v), "sim", None))
        if not baselines_done:
            for d in devs:
                if d["channel"] == "waveform":
                    for i in range(n_baseline):
                        capture(d, dmg, ts_ms=ts + i * 60_000, rng=rng, temp_c=temp, baseline=True, label="healthy",
                                notes="Commissioning baseline (simulated)")
            baselines_done = True
        if ts >= next_wave:
            next_wave += wave_every_s * 1000
            for d in devs:
                if d["channel"] == "waveform":
                    capture(d, dmg, ts_ms=ts, rng=rng, temp_c=temp)
        if ts >= next_health:
            next_health += health_every_s * 1000
            if len(readings) > 5000:
                db.run_many("INSERT INTO readings(device_id,ts_ms,value,source,batch_id) VALUES(?,?,?,?,?)", readings)
                readings = []
            if readings:
                db.run_many("INSERT INTO readings(device_id,ts_ms,value,source,batch_id) VALUES(?,?,?,?,?)", readings)
                readings = []
            refresh_health(sid, at_ms=ts, historic=True)
        ts += step_s * 1000
    if readings:
        db.run_many("INSERT INTO readings(device_id,ts_ms,value,source,batch_id) VALUES(?,?,?,?,?)", readings)
    # final state: leave sim_state at the end-of-history condition so live ticks continue smoothly
    db.run("INSERT INTO sim_state(structure_id,scenario,damage,moisture_boost,speed,updated_ms) VALUES(?,?,?,?,?,?) "
           "ON CONFLICT(structure_id) DO UPDATE SET damage=excluded.damage, moisture_boost=excluded.moisture_boost, updated_ms=excluded.updated_ms",
           (sid, "healthy", damage_end, moisture_end, 0.0, end))
    db.run(f"UPDATE devices SET last_seen_ms=? WHERE structure_id=? AND source_type='simulated'", (end, sid))
    refresh_health(sid, at_ms=end, historic=True)


# ------------------------------------------------------------------ 10 Hz demo stream for the specimen rig (DEMO data)
_p2p = {}          # structure_id -> {"sim": TapSim, "expires": epoch_s, "scenario": str}
_p2p_lock = threading.Lock()


def p2p_status(sid):
    with _p2p_lock:
        e = _p2p.get(sid)
        if not e or time.time() > e["expires"]:
            return {"running": False, "scenario": None, "scenarios": impact.SCENARIOS}
        return {"running": True, "scenario": e["scenario"], "expires_in_s": int(e["expires"] - time.time()),
                "scenarios": impact.SCENARIOS}


def p2p_control(sid, running, scenario="normal", minutes=30):
    if scenario not in impact.SCENARIOS:
        raise ValueError("Unknown demo scenario.")
    if not impact.supports(sid):
        raise ValueError("This structure has no 3-channel piezo rig.")
    with _p2p_lock:
        if running:
            old = _p2p.get(sid)
            sim = old["sim"] if old else impact.TapSim(scenario)
            sim.scenario = scenario
            _p2p[sid] = {"sim": sim, "expires": time.time() + minutes * 60, "scenario": scenario}
        else:
            _p2p.pop(sid, None)
    return p2p_status(sid)


def _p2p_loop():
    last_seen = 0.0
    while not _stop.wait(0.1):
        try:
            now_s = time.time()
            with _p2p_lock:
                items = [(sid, e) for sid, e in _p2p.items() if now_s <= e["expires"]]
                for sid in [sid for sid, e in _p2p.items() if now_s > e["expires"]]:
                    _p2p.pop(sid, None)
            for sid, e in items:
                vals = e["sim"].packet()
                ts = int(now_s * 1000)
                impact.write_packet(sid, vals, ts, "sim")
                events.publish("p2p", {"structure_id": sid, "ts_ms": ts, "s1": vals[0], "s2": vals[1], "s3": vals[2], "source": "sim"})
                if now_s - last_seen > 2:
                    last_seen = now_s
                    ids = [d["id"] for d in impact.devices(sid)]
                    db.run(f"UPDATE devices SET last_seen_ms=? WHERE id IN ({','.join('?' for _ in ids)})", [ts] + ids)
        except Exception:
            import traceback
            traceback.print_exc()


# ------------------------------------------------------------------ control + loop
def set_scenario(sid, scenario, damage=None, speed=None):
    if scenario not in SCENARIOS:
        raise ValueError("Unknown scenario")
    st = _state_row(sid)
    f = {"scenario": scenario, "updated_ms": db.now_ms()}
    if damage is not None:
        f["damage"] = max(0.0, min(0.8, float(damage)))
    if speed is not None:
        f["speed"] = float(speed)
    db.update("sim_state", sid, f, key="structure_id")
    return state_of(sid)


def inject(sid, kind):
    st = _state_row(sid)
    if kind == "crack_step":
        db.update("sim_state", sid, {"damage": min(0.8, st["damage"] + 0.1), "updated_ms": db.now_ms()}, key="structure_id")
    elif kind == "overload_vehicle":
        _pending_overload.add(sid)
    elif kind == "moisture_spike":
        db.update("sim_state", sid, {"moisture_boost": min(10.0, st["moisture_boost"] + 4.0), "updated_ms": db.now_ms()}, key="structure_id")
    elif kind == "reset":
        db.update("sim_state", sid, {"damage": 0.0, "moisture_boost": 0.0, "scenario": "healthy", "updated_ms": db.now_ms()}, key="structure_id")
    else:
        raise ValueError("Unknown injection")
    _last_health[sid] = 0
    return state_of(sid)


def state_of(sid):
    st = _state_row(sid)
    return {"structure_id": sid, "scenario": st["scenario"], "damage": round(st["damage"], 3),
            "moisture_boost": round(st["moisture_boost"], 2), "speed": st["speed"]}


def status():
    return {"running": _state["running"], "interval_s": _state["interval"], "ticks": _state["ticks"],
            "last_tick_ms": _state["last_tick_ms"], "scenarios": SCENARIOS,
            "structures": [state_of(s["id"]) for s in db.q("SELECT id FROM structures")]}


def control(running=None, interval=None):
    if interval is not None:
        _state["interval"] = max(1.0, min(30.0, float(interval)))
    if running is not None:
        _state["running"] = bool(running)
        db.set_setting("sim.running", bool(running))
    return status()


def prune():
    cutoff = db.now_ms() - config.SIM_RETENTION_HOURS * 3600_000
    db.run("DELETE FROM readings WHERE source='sim' AND ts_ms<?", (cutoff,))
    db.run("DELETE FROM waveforms WHERE source='sim' AND is_baseline=0 AND label IS NULL AND ts_ms<?",
           (db.now_ms() - 48 * 3600_000,))
    for d in db.q("SELECT id,config_json FROM devices WHERE kind='piezo'"):
        if json.loads(d["config_json"] or "{}").get("mode") == "p2p":
            db.run("DELETE FROM readings WHERE device_id=? AND ts_ms<?", (d["id"], db.now_ms() - 6 * 3600_000))


def start():
    if _state.get("thread"):
        return
    _state["running"] = bool(db.get_setting("sim.running", config.SIM_AUTOSTART))
    last_house = [0]

    def loop():
        while not _stop.wait(_state["interval"]):
            try:
                if _state["running"]:
                    for s in sim_structures():
                        tick(s["id"])
                    _state["ticks"] += 1
                    _state["last_tick_ms"] = db.now_ms()
                if time.time() - last_house[0] > 120:
                    last_house[0] = time.time()
                    prune()
                    alerts_engine.check_offline_devices()
            except Exception as e:  # keep the simulator alive
                import traceback
                traceback.print_exc()
                _state["last_error"] = str(e)
    t = threading.Thread(target=loop, name="simulator", daemon=True)
    t.start()
    threading.Thread(target=_p2p_loop, name="p2p-demo", daemon=True).start()
    _state["thread"] = t
