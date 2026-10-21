"""Machine-learning layer.

Honesty note (also shown in the UI under Intelligence):
  * Vibration autoencoder  - a REAL scikit-learn model, but trained on SIMULATED healthy data.
  * Health-index forest    - a REAL Random Forest, trained on SIMULATED labels produced by the rule-based
                             scoring framework. It demonstrates the pipeline; it is not a validated predictor.
  * Fatigue (Miner's rule) - REAL analytical calculation (rainflow + S-N curve). The deck's LSTM needs labelled
                             fatigue data we do not have, so it is a SLOT, not implemented.
  * Load regression        - REAL ridge regression; trains on paired strain/WIM readings if present, else on
                             simulated pairs.
  * Crack detector (CNN/YOLO) - SLOT. The working detector is classical OpenCV/scikit-image (see vision.py).
"""
import json
import pickle
import threading

import numpy as np

from .. import config

_lock = threading.Lock()
_cache = {}

FEATURES = ["freq_ratio", "log_rms_ratio", "centroid_ratio", "log_damping_ratio", "spectral_corr"]


def features_from_compare(cmp: dict):
    dr = cmp.get("damping_ratio")
    sc = cmp.get("spectral_corr")
    return [1 + cmp["freq_shift_pct"] / 100.0,
            float(np.log(max(cmp["rms_ratio"], 1e-3))),
            1 + cmp["centroid_shift_pct"] / 100.0,
            float(np.log(dr)) if dr else 0.0,
            sc if sc is not None else 0.9]


# ---------------------------------------------------------------- autoencoder (anomaly)
def _train_autoencoder():
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler
    from . import dsp, simulator

    rng = np.random.default_rng(7)
    X = []
    for prof in simulator.WAVE_PROFILES.values():
        feats_base = []
        for _ in range(6):
            w = simulator.synth_waveform(prof, 0.0, rng, temp_c=25)
            feats_base.append(dsp.analyze(w, prof["fs"]))
        base = dsp.median_features(feats_base)
        for _ in range(160):
            temp = rng.uniform(8, 42)
            w = simulator.synth_waveform(prof, 0.0, rng, temp_c=temp)
            X.append(features_from_compare(dsp.compare(base, dsp.analyze(w, prof["fs"]))))
    X = np.array(X)
    sc = StandardScaler().fit(X)
    Z = sc.transform(X)
    net = MLPRegressor(hidden_layer_sizes=(8, 3, 8), activation="tanh", max_iter=3000,
                       random_state=0, alpha=1e-3).fit(Z, Z)
    err = ((net.predict(Z) - Z) ** 2).mean(axis=1)
    thr = float(np.percentile(err, 99))
    # quick self-check against simulated damage levels (NOT field validation)
    perf = {}
    for dmg in (0.05, 0.1, 0.2, 0.35):
        hit = []
        for prof in simulator.WAVE_PROFILES.values():
            fb = dsp.median_features([dsp.analyze(simulator.synth_waveform(prof, 0.0, rng), prof["fs"]) for _ in range(6)])
            for _ in range(60):
                w = simulator.synth_waveform(prof, dmg, rng, temp_c=rng.uniform(8, 42))
                f = features_from_compare(dsp.compare(fb, dsp.analyze(w, prof["fs"])))
                z = sc.transform([f])
                hit.append(float(((net.predict(z) - z) ** 2).mean()) > thr)
        perf[str(dmg)] = round(float(np.mean(hit)), 3)
    model = {"scaler": sc, "net": net, "thr": thr,
             "metrics": {"train_samples": int(len(X)), "false_alarm_rate_target": 0.01,
                         "detection_rate_by_simulated_damage": perf}}
    with open(config.MODEL_DIR / "autoencoder.pkl", "wb") as fh:
        pickle.dump(model, fh)
    return model


def _load(name, trainer):
    with _lock:
        if name in _cache:
            return _cache[name]
        p = config.MODEL_DIR / f"{name}.pkl"
        m = None
        if p.exists():
            try:
                with open(p, "rb") as fh:
                    m = pickle.load(fh)
            except Exception:
                m = None
        if m is None:
            m = trainer()
        _cache[name] = m
        return m


def anomaly_score(cmp: dict) -> float:
    """0 = looks like healthy baseline behaviour, 1 = strongly anomalous."""
    m = _load("autoencoder", _train_autoencoder)
    z = m["scaler"].transform([features_from_compare(cmp)])
    err = float(((m["net"].predict(z) - z) ** 2).mean())
    return float(min(1.0, err / (2 * m["thr"])))


def retrain(name):
    with _lock:
        _cache.pop(name, None)
        p = config.MODEL_DIR / f"{name}.pkl"
        if p.exists():
            p.unlink()
    return {"autoencoder": lambda: _load("autoencoder", _train_autoencoder),
            "health_forest": lambda: _load("health_forest", _train_forest),
            "load_regression": lambda: load_model(force=True)}[name]()


# ---------------------------------------------------------------- Random-forest health index
COMP_KEYS = ["vibration", "cracks", "strain_fatigue", "deflection", "environment"]


def _train_forest():
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import train_test_split
    from . import health

    rng = np.random.default_rng(11)
    X = rng.uniform(0, 100, size=(4000, 5))
    X[rng.random(X.shape) < 0.5] = np.nan  # random missing components
    y = [health.combine({k: (None if np.isnan(v) else v) for k, v in zip(COMP_KEYS, row)})[0] for row in X]
    keep = np.array([v is not None for v in y])  # rows with every component missing have no label
    X = X[keep]
    y = np.array([v for v in y if v is not None], dtype=float)
    y = y + rng.normal(0, 1.5, size=len(y))
    Xf = _fill(X)
    Xtr, Xte, ytr, yte = train_test_split(Xf, y, test_size=0.2, random_state=1)
    rf = RandomForestRegressor(n_estimators=120, max_depth=9, random_state=0, n_jobs=1).fit(Xtr, ytr)
    r2 = float(rf.score(Xte, yte))
    model = {"rf": rf, "metrics": {"r2_holdout": round(r2, 4), "train_rows": int(len(Xtr)),
                                   "label_source": "rule-based scoring framework + noise (SIMULATED labels)",
                                   "importances": dict(zip(COMP_KEYS, [round(float(v), 3) for v in rf.feature_importances_]))}}
    with open(config.MODEL_DIR / "health_forest.pkl", "wb") as fh:
        pickle.dump(model, fh)
    return model


def _fill(X):
    X = np.array(X, dtype=float)
    out = X.copy()
    for i, row in enumerate(X):
        pres = row[~np.isnan(row)]
        fill = pres.mean() if len(pres) else 100.0
        out[i, np.isnan(row)] = fill
    return out


def forest_estimate(components: dict):
    m = _load("health_forest", _train_forest)
    row = [[components.get(k) if components.get(k) is not None else np.nan for k in COMP_KEYS]]
    return float(np.clip(m["rf"].predict(_fill(row))[0], 0, 100))


# ---------------------------------------------------------------- fatigue (rainflow + Miner)
def rainflow(series):
    """ASTM E1049 style 3-point rainflow. Returns list of (range, cycle_count)."""
    x = [float(v) for v in series]
    if len(x) < 3:
        return []
    pts = [x[0]]
    for v in x[1:]:
        if v == pts[-1]:
            continue
        if len(pts) >= 2 and (pts[-1] - pts[-2]) * (v - pts[-1]) > 0:
            pts[-1] = v
        else:
            pts.append(v)
    stack, out = [], []
    for p in pts:
        stack.append(p)
        while len(stack) >= 3:
            X = abs(stack[-1] - stack[-2])
            Y = abs(stack[-2] - stack[-3])
            if X < Y:
                break
            if len(stack) == 3:
                out.append((Y, 0.5))
                stack.pop(0)
            else:
                out.append((Y, 1.0))
                del stack[-3:-1]
    for i in range(len(stack) - 1):
        out.append((abs(stack[i + 1] - stack[i]), 0.5))
    return out


def miner_damage(strain_ue, noise_floor_mpa=8.0, es_mpa=200000.0, detail_mpa=160.0, n_ref=2e6, m=3.0):
    """Miner's-rule damage for the observed record. Strain in microstrain -> steel stress range (MPa).
    S-N: N = n_ref * (detail/range)^m (detail category 160 / 2e6 cycles, Eurocode-style). Returns (D, cycles_counted)."""
    D, cyc = 0.0, 0.0
    for rng_ue, cnt in rainflow(strain_ue):
        ds = rng_ue * 1e-6 * es_mpa
        if ds < noise_floor_mpa:
            continue
        D += cnt / (n_ref * (detail_mpa / ds) ** m)
        cyc += cnt
    return D, cyc


# ---------------------------------------------------------------- load regression
def load_model(force=False, pairs=None):
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import train_test_split
    with _lock:
        if not force and "load" in _cache:
            return _cache["load"]
    source = "paired strain/WIM readings from the database"
    if pairs is None or len(pairs) < 30:
        rng = np.random.default_rng(3)
        w = rng.lognormal(np.log(180), 0.45, 400)
        s = 0.55 * w + rng.normal(0, 8, 400)
        pairs = list(zip(s, w))
        source = "SIMULATED strain/weight pairs (no real WIM data yet)"
    P = np.array(pairs, dtype=float)
    Xtr, Xte, ytr, yte = train_test_split(P[:, :1], P[:, 1], test_size=0.25, random_state=0)
    r = Ridge(alpha=1.0).fit(Xtr, ytr)
    m = {"model": r, "metrics": {"r2_holdout": round(float(r.score(Xte, yte)), 4), "pairs": int(len(P)),
                                 "training_data": source}}
    with _lock:
        _cache["load"] = m
    return m


def predict_load_kn(strain_peak_ue):
    return float(load_model()["model"].predict([[strain_peak_ue]])[0])


def model_metrics():
    ae = _load("autoencoder", _train_autoencoder)
    hf = _load("health_forest", _train_forest)
    ld = load_model()
    return ae["metrics"], hf["metrics"], ld["metrics"]
