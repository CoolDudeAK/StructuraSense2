"""Demo data. Three DEMO assets (fictional - they are not real structures) + demo users.
All history is SIMULATED and tagged source='sim'."""
import json
import os

import cv2

from .. import auth, config, db
from . import impact, simulator, synth_images, vision

DEMO_PASSWORD = os.environ.get("SS_DEMO_PASSWORD", "Sense@2026")

STRUCTURES = [
    dict(id="STR-001", name="Lab Specimen S1 (Arduino UNO + 3 piezo sensors)", kind="specimen", location="Structures lab test bench",
         state=None, lat=None, lon=None, built_year=2026, material="Concrete specimen / block with 3 piezo sensors", span_m=0.5,
         owner_agency="Team VitaForge", is_demo=0,
         description="The real proof of concept: a concrete specimen with three piezo sensors read by an Arduino UNO. "
                     "Open Impact Lab to connect the rig, calibrate a baseline and run Intact / Damaged impact trials. "
                     "Until the Arduino is connected, everything shown here is DEMO data.",
         limits=dict(strain_limit_ue=400, deflection_ratio=800, wim_limit_kn=400, cycles_per_day=20000),
         zones=["Sensor S1 region", "Sensor S2 region", "Sensor S3 region"],
         devices=[
             dict(id="piezo-s1", name="Piezo sensor 1 (A0)", kind="piezo", channel="scalar", unit="ADC p2p", zone=0, x=.2, y=.35,
                  cfg=dict(mode="p2p", sensor=1, traffic=False)),
             dict(id="piezo-s2", name="Piezo sensor 2 (A1)", kind="piezo", channel="scalar", unit="ADC p2p", zone=1, x=.5, y=.6,
                  cfg=dict(mode="p2p", sensor=2, traffic=False)),
             dict(id="piezo-s3", name="Piezo sensor 3 (A2)", kind="piezo", channel="scalar", unit="ADC p2p", zone=2, x=.8, y=.35,
                  cfg=dict(mode="p2p", sensor=3, traffic=False)),
         ],
         hist=None, scenario=("healthy", 0.0), impact_seed=True),
    dict(id="STR-002", name="Demo Road Bridge RB-12 (PSC girder, 3 spans)", kind="bridge",
         location="State highway corridor, Bihar (demo asset)", state="Bihar", lat=25.21, lon=84.99, built_year=1998,
         material="Prestressed concrete girders, RCC piers", span_m=36.0, owner_agency="Demo agency (fictional)", is_demo=1,
         description="A fictional three-span road bridge used to demonstrate gradual stiffness loss: its natural frequency "
                     "is drifting down and one crack has been photographed at Span 2.",
         limits=dict(strain_limit_ue=400, deflection_ratio=800, wim_limit_kn=400, cycles_per_day=20000),
         zones=["Abutment A1", "Span 1", "Pier P1", "Span 2", "Pier P2", "Span 3", "Abutment A2"],
         devices=[
             dict(id="acc-01", name="Accelerometer - Span 2 mid", kind="accelerometer", channel="waveform", unit="g", zone=3, x=.5, y=.75,
                  fs=100, cfg=dict(profile="bridge", f0=4.8)),
             dict(id="acc-02", name="Accelerometer - Span 3 mid", kind="accelerometer", channel="waveform", unit="g", zone=5, x=.83, y=.75,
                  fs=100, cfg=dict(profile="bridge", f0=4.85)),
             dict(id="str-01", name="Strain gauge - Span 2 girder", kind="strain", channel="scalar", unit="µε", zone=3, x=.48, y=.7,
                  cfg=dict(gain=0.55)),
             dict(id="str-02", name="Strain gauge - Span 1 girder", kind="strain", channel="scalar", unit="µε", zone=1, x=.2, y=.7,
                  cfg=dict(gain=0.5)),
             dict(id="str-03", name="Strain gauge - Span 3 girder", kind="strain", channel="scalar", unit="µε", zone=5, x=.8, y=.7,
                  cfg=dict(gain=0.52)),
             dict(id="lvdt-01", name="LVDT deflection - Span 2", kind="lvdt", channel="scalar", unit="mm", zone=3, x=.52, y=.9,
                  cfg=dict(c=0.06)),
             dict(id="temp-01", name="Deck temperature", kind="temperature", channel="scalar", unit="°C", zone=1, x=.15, y=.15,
                  cfg=dict(traffic=False)),
             dict(id="moist-01", name="Moisture probe - Pier P1", kind="moisture", channel="scalar", unit="%", zone=2, x=.38, y=.55,
                  cfg=dict(base=5.4, traffic=False)),
             dict(id="moist-02", name="Moisture probe - Span 3 soffit", kind="moisture", channel="scalar", unit="%", zone=5, x=.78, y=.88,
                  cfg=dict(base=5.6, traffic=False)),
             dict(id="wim-01", name="Weigh-in-motion - approach", kind="wim", channel="scalar", unit="kN", zone=0, x=.02, y=.1, cfg=dict()),
             dict(id="rf-01", name="RF coil - Span 2 soffit (experimental)", kind="rf_coil", channel="scalar", unit="kHz", zone=3, x=.44, y=.62,
                  cfg=dict(f0=1000.0, traffic=False)),
             dict(id="rf-02", name="RF coil - Pier P1 (experimental)", kind="rf_coil", channel="scalar", unit="kHz", zone=2, x=.34, y=.42,
                  cfg=dict(f0=1000.0, traffic=False)),
             dict(id="cam-01", name="CCTV camera - Span 2 underside", kind="camera", channel="image", unit=None, zone=3, x=.55, y=.95, cfg=dict()),
         ],
         hist=dict(hours=72, step=300, d0=0.02, d1=0.30, m1=1.6, wave_every=7200), scenario=("gradual_degradation", 4e-6),
         cracks=[dict(sample="sample_fine.png", zone=3, hours_ago=30)]),
    dict(id="STR-003", name="Demo RCC Flyover FO-3 (urban)", kind="flyover", location="Urban corridor, Delhi NCR (demo asset)",
         state="Delhi", lat=28.58, lon=77.21, built_year=2009, material="RCC deck slab on box girders", span_m=24.0,
         owner_agency="Demo agency (fictional)", is_demo=1,
         description="A fictional urban flyover used to demonstrate moisture ingress: deck moisture has been rising for days "
                     "while the structure itself is still stiff.",
         limits=dict(strain_limit_ue=400, deflection_ratio=800, wim_limit_kn=400, cycles_per_day=26000),
         zones=["Ramp A", "Span 1", "Span 2", "Span 3", "Ramp B"],
         devices=[
             dict(id="acc-01", name="Accelerometer - Span 2", kind="accelerometer", channel="waveform", unit="g", zone=2, x=.5, y=.75,
                  fs=100, cfg=dict(profile="flyover", f0=3.1)),
             dict(id="str-01", name="Strain gauge - Span 2", kind="strain", channel="scalar", unit="µε", zone=2, x=.5, y=.7, cfg=dict(gain=0.45)),
             dict(id="str-02", name="Strain gauge - Span 3", kind="strain", channel="scalar", unit="µε", zone=3, x=.7, y=.7, cfg=dict(gain=0.47)),
             dict(id="lvdt-01", name="LVDT deflection - Span 2", kind="lvdt", channel="scalar", unit="mm", zone=2, x=.5, y=.9, cfg=dict(c=0.05)),
             dict(id="temp-01", name="Deck temperature", kind="temperature", channel="scalar", unit="°C", zone=1, x=.25, y=.12,
                  cfg=dict(traffic=False)),
             dict(id="moist-01", name="Moisture probe - Span 1 deck", kind="moisture", channel="scalar", unit="%", zone=1, x=.28, y=.3,
                  cfg=dict(base=5.5, traffic=False)),
             dict(id="moist-02", name="Moisture probe - Span 3 deck", kind="moisture", channel="scalar", unit="%", zone=3, x=.72, y=.3,
                  cfg=dict(base=5.5, traffic=False)),
             dict(id="wim-01", name="Weigh-in-motion - ramp A", kind="wim", channel="scalar", unit="kN", zone=0, x=.04, y=.12, cfg=dict()),
             dict(id="rf-01", name="RF coil - Span 2 deck (experimental)", kind="rf_coil", channel="scalar", unit="kHz", zone=2, x=.55, y=.5,
                  cfg=dict(f0=1000.0, traffic=False)),
             dict(id="cam-01", name="Drone survey - Span 1 deck", kind="camera", channel="image", unit=None, zone=1, x=.3, y=.05, cfg=dict()),
         ],
         hist=dict(hours=72, step=300, d0=0.0, d1=0.04, m1=5.2, wave_every=7200), scenario=("healthy", 0.0),
         cracks=[dict(sample="sample_hairline.png", zone=1, hours_ago=20)]),
]


def seed_impact(sid):
    """DEMO baseline + trials for the specimen so Impact Lab is not empty. All labelled DEMO/SIMULATION DATA."""
    import numpy as np
    rng = np.random.default_rng(42)
    now = db.now_ms()
    base_trials = []
    for i in range(20):
        v = [impact.p2p(c) for c in impact.simulate_trial_values("normal", rng)]
        base_trials.append({"s1": v[0], "s2": v[1], "s3": v[2]})
    b = impact.calc_baseline(base_trials)
    db.insert("impact_baselines", {"structure_id": sid, **b, "num_trials": 20, "specimen_id": "specimen-1",
                                   "created_ms": now - 30 * 3600_000, "source": "sim"})
    plan = [("Intact", "normal")] * 4 + [("Damaged", "anomaly")] * 3 + [("Damaged", "severe")] * 2 + [("Intact", "normal")] * 3
    for i, (cond, sc) in enumerate(plan):
        cols = impact.simulate_trial_values(sc, rng)
        summ = impact.summarize(*cols)
        cur = {f"sensor{k}": summ[f"sensor{k}"]["peak_to_peak"] for k in (1, 2, 3)}
        ts = now - int((len(plan) - i) * 2.2 * 3600_000)
        impact.save_trial(sid, cond, cur, impact.mean([summ[f"sensor{k}"]["mean"] for k in (1, 2, 3)]),
                          max(summ[f"sensor{k}"]["max"] for k in (1, 2, 3)), min(summ[f"sensor{k}"]["min"] for k in (1, 2, 3)),
                          "sim", len(cols[0]), 5, ts_ms=ts, notes="Demo trial (simulated)")


def seeded():
    return db.one("SELECT COUNT(*) n FROM structures")["n"] > 0


def create_users():
    for email, name, role in (("admin@vitaforge.demo", "Admin (demo)", "admin"),
                              ("engineer@vitaforge.demo", "Engineer (demo)", "engineer"),
                              ("viewer@vitaforge.demo", "Viewer (demo)", "viewer")):
        if not db.one("SELECT id FROM users WHERE email=?", (email,)):
            db.insert("users", {"id": db.uid(), "email": email, "name": name, "role": role,
                                "pw_hash": auth.hash_password(DEMO_PASSWORD), "created_ms": db.now_ms()})


def ensure_spec_devices(hours=48):
    """Databases made by an earlier version lack the newer demo sensors (WIM on the flyover, RF coils). Add them,
    with a short simulated history, so every structure shows all seven channels. Idempotent."""
    import numpy as np
    added = 0
    for s in STRUCTURES:
        if not db.one("SELECT id FROM structures WHERE id=?", (s["id"],)):
            continue
        zids = {z["idx"]: z["id"] for z in db.q("SELECT id,idx FROM zones WHERE structure_id=?", (s["id"],))}
        stt = db.one("SELECT * FROM sim_state WHERE structure_id=?", (s["id"],)) or {"damage": 0.0, "moisture_boost": 0.0}
        for d in s["devices"]:
            did = f"s{int(s['id'][-3:])}-{d['id']}"
            if db.one("SELECT id FROM devices WHERE id=?", (did,)):
                continue
            now = db.now_ms()
            db.insert("devices", {"id": did, "structure_id": s["id"], "zone_id": zids.get(d["zone"]) if d["zone"] is not None else None,
                                  "name": d["name"], "kind": d["kind"], "channel": d["channel"], "unit": d["unit"], "source_type": "simulated",
                                  "pos_x": d["x"], "pos_y": d["y"], "fs": d.get("fs"), "config_json": json.dumps(d["cfg"]),
                                  "last_seen_ms": now, "created_ms": now})
            rng = np.random.default_rng(sum(map(ord, did)))
            rows = []
            steps = int(hours * 12)
            for i in range(steps):
                ts = now - (steps - i) * 300_000
                frac = i / max(1, steps - 1)
                st = {"damage": stt["damage"] * (0.8 + 0.2 * frac), "moisture_boost": stt["moisture_boost"] * frac}
                W = simulator.vehicle_weight(rng) if rng.random() < 0.85 else None
                v = simulator.scalar_value({"kind": d["kind"]}, d["cfg"], st, ts, simulator.temperature_c(ts, rng),
                                           W if d["cfg"].get("traffic", True) else None, rng)
                if v is not None:
                    rows.append((did, ts, float(v), "sim", None))
            if rows:
                db.run_many("INSERT INTO readings(device_id,ts_ms,value,source,batch_id) VALUES(?,?,?,?,?)", rows)
            added += 1
    return added


def seed_all(verbose=False):
    create_users()
    if seeded():
        if ensure_spec_devices():
            for s in db.q("SELECT id FROM structures WHERE is_demo=1"):
                simulator.refresh_health(s["id"], at_ms=db.now_ms(), historic=True)
        return False
    samples = synth_images.ensure_samples(config.SAMPLE_DIR)
    now = db.now_ms()
    for s in STRUCTURES:
        db.insert("structures", {"id": s["id"], "name": s["name"], "kind": s["kind"], "location": s["location"], "state": s["state"],
                                 "lat": s["lat"], "lon": s["lon"], "built_year": s["built_year"], "material": s["material"],
                                 "span_m": s["span_m"], "owner_agency": s["owner_agency"], "description": s["description"],
                                 "is_demo": s["is_demo"], "data_mode": "all", "limits_json": json.dumps(s["limits"]), "created_ms": now})
        zids = []
        n = len(s["zones"])
        for i, zn in enumerate(s["zones"]):
            zid = f"{s['id']}-Z{i+1}"
            zids.append(zid)
            db.insert("zones", {"id": zid, "structure_id": s["id"], "idx": i, "name": zn, "x0": i / n, "x1": (i + 1) / n})
        for d in s["devices"]:
            db.insert("devices", {"id": f"s{int(s['id'][-3:])}-{d['id']}", "structure_id": s["id"],
                                  "zone_id": zids[d["zone"]] if d["zone"] is not None else None, "name": d["name"], "kind": d["kind"],
                                  "channel": d["channel"], "unit": d["unit"], "source_type": "simulated", "pos_x": d["x"], "pos_y": d["y"],
                                  "fs": d.get("fs"), "config_json": json.dumps(d["cfg"]), "created_ms": now})
        sc, sp = s["scenario"]
        db.insert("sim_state", {"structure_id": s["id"], "scenario": sc, "damage": 0.0, "moisture_boost": 0.0, "speed": sp, "updated_ms": now})
        for c in s.get("cracks", []):
            img = cv2.imread(str(config.SAMPLE_DIR / c["sample"]))
            vision.run_and_store(s["id"], zids[c["zone"]], img, synth_images.SCALE_PX_PER_MM, c["sample"], origin="sample",
                                 ts_ms=now - c["hours_ago"] * 3600_000)
        h = s["hist"]
        if h:
            simulator.generate_history(s["id"], h["hours"], step_s=h["step"], damage_start=h["d0"], damage_end=h["d1"],
                                       moisture_end=h["m1"], wave_every_s=h["wave_every"], seed=int(s["id"][-3:]))
            # history generation resets scenario to 'healthy'; restore the intended live scenario
            db.update("sim_state", s["id"], {"scenario": sc, "speed": sp}, key="structure_id")
        if s.get("impact_seed"):
            seed_impact(s["id"])
            simulator.refresh_health(s["id"], at_ms=db.now_ms(), historic=True)
        if verbose:
            print("seeded", s["id"])
    db.set_setting("sim.running", config.SIM_AUTOSTART)
    return True


def reset_all():
    for t in ("impact_trials", "impact_calibration", "impact_baselines", "sync_queue", "csv_imports", "maintenance_tasks", "alerts", "health_scores", "crack_analyses", "waveforms",
              "readings", "sim_state", "devices", "zones", "structures"):
        db.run(f"DELETE FROM {t}")
    for f in config.UPLOAD_DIR.glob("*"):
        try:
            f.unlink()
        except OSError:
            pass
    return seed_all()
