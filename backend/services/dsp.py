"""Signal processing for vibration / piezo waveforms. REAL implementation (NumPy/SciPy)."""
import numpy as np
from scipy import signal as sps
from scipy import stats


def pack(samples) -> bytes:
    return np.asarray(samples, dtype="<f4").tobytes()


def unpack(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype="<f4").astype(float)


def _spectrum(x, fs):
    n = len(x)
    nper = int(min(n, max(256, 2 ** int(np.floor(np.log2(max(n // 2, 2)))))))
    f, p = sps.welch(x, fs=fs, window="hann", nperseg=nper, noverlap=nper // 2, detrend="constant",
                     scaling="spectrum")
    return f, np.sqrt(p)  # amplitude-like spectrum


def analyze(samples, fs, fmin=None):
    """Feature extraction used by the health index and Signal Lab."""
    x = np.asarray(samples, dtype=float)
    if len(x) < 64 or fs <= 0:
        raise ValueError("Need at least 64 samples and a positive sample rate.")
    x = x - x.mean()
    rms = float(np.sqrt(np.mean(x ** 2)))
    peak = float(np.max(np.abs(x)))
    crest = float(peak / rms) if rms > 0 else 0.0
    kurt = float(stats.kurtosis(x, fisher=False)) if rms > 0 else 0.0
    f, a = _spectrum(x, fs)
    fmin = fmin if fmin is not None else max(f[1] * 2, fs * 0.004)
    mask = f >= fmin
    ff, aa = f[mask], a[mask]
    if aa.sum() <= 0:
        return dict(rms=rms, peak=peak, crest=crest, kurtosis=kurt, dom_freq=0.0, centroid=0.0,
                    damping=None, bands=[0, 0, 0, 0])
    k = int(np.argmax(aa))
    dom = float(ff[k])
    if 0 < k < len(aa) - 1:  # parabolic interpolation on log amplitude
        y0, y1, y2 = np.log(aa[k - 1] + 1e-18), np.log(aa[k] + 1e-18), np.log(aa[k + 1] + 1e-18)
        den = (y0 - 2 * y1 + y2)
        if den != 0:
            dom = float(ff[k] + 0.5 * (y0 - y2) / den * (ff[1] - ff[0]))
    centroid = float((ff * aa).sum() / aa.sum())
    nyq = fs / 2
    edges = [0, 0.1 * nyq, 0.25 * nyq, 0.5 * nyq, nyq + 1]
    pw = a ** 2
    tot = pw.sum() or 1.0
    bands = [float(pw[(f >= edges[i]) & (f < edges[i + 1])].sum() / tot) for i in range(4)]
    return dict(rms=rms, peak=peak, crest=crest, kurtosis=kurt, dom_freq=dom, centroid=centroid,
                damping=_half_power_damping(ff, aa, k), bands=bands)


def _half_power_damping(ff, aa, k):
    """Damping ratio from the -3 dB bandwidth around the dominant peak (None if it cannot be measured)."""
    try:
        peak = aa[k]
        half = peak / np.sqrt(2)
        i = k
        while i > 0 and aa[i] > half:
            i -= 1
        j = k
        while j < len(aa) - 1 and aa[j] > half:
            j += 1
        if i == 0 or j == len(aa) - 1:
            return None
        f1 = ff[i] + (half - aa[i]) / (aa[i + 1] - aa[i]) * (ff[i + 1] - ff[i])
        f2 = ff[j - 1] + (aa[j - 1] - half) / (aa[j - 1] - aa[j]) * (ff[j] - ff[j - 1])
        z = float((f2 - f1) / (2 * ff[k]))
        return z if 0 < z < 0.5 else None
    except Exception:
        return None


def ui_waveform(samples, max_points=900):
    """Min/max decimation so spikes survive downsampling. Returns (indices, values)."""
    x = np.asarray(samples, dtype=float)
    n = len(x)
    if n <= max_points:
        return list(range(n)), [round(float(v), 5) for v in x]
    step = int(np.ceil(n / (max_points / 2)))
    idx, val = [], []
    for s in range(0, n, step):
        seg = x[s:s + step]
        a, b = int(np.argmin(seg)), int(np.argmax(seg))
        for j in sorted({a, b}):
            idx.append(s + j)
            val.append(round(float(seg[j]), 5))
    return idx, val


def ui_spectrum(samples, fs, max_points=400):
    x = np.asarray(samples, dtype=float)
    x = x - x.mean()
    f, a = _spectrum(x, fs)
    if len(f) > max_points:
        step = int(np.ceil(len(f) / max_points))
        f = f[::step]
        a = np.array([a[i:i + step].max() for i in range(0, len(a), step)])[:len(f)]
    return [round(float(v), 4) for v in f], [float(v) for v in a]


def compare(base: dict, cur: dict, base_spec=None, cur_spec=None):
    """Compare current features against a baseline. Negative frequency shift = stiffness loss."""
    out = {}
    out["freq_shift_pct"] = (cur["dom_freq"] - base["dom_freq"]) / base["dom_freq"] * 100 if base["dom_freq"] else 0.0
    out["rms_ratio"] = cur["rms"] / base["rms"] if base["rms"] else 1.0
    out["centroid_shift_pct"] = (cur["centroid"] - base["centroid"]) / base["centroid"] * 100 if base["centroid"] else 0.0
    bd, cd = base.get("damping"), cur.get("damping")
    out["damping_ratio"] = (cd / bd) if (bd and cd) else None
    if base_spec and cur_spec:
        fb, ab = base_spec
        fc, ac = cur_spec
        grid = np.linspace(max(fb[1], fc[1]), min(fb[-1], fc[-1]), 200)
        a1 = np.interp(grid, fb, ab)
        a2 = np.interp(grid, fc, ac)
        d = np.linalg.norm(a1) * np.linalg.norm(a2)
        out["spectral_corr"] = float(np.dot(a1, a2) / d) if d else 1.0
    else:
        out["spectral_corr"] = None
    return out


def median_features(feats):
    keys = ["rms", "peak", "crest", "kurtosis", "dom_freq", "centroid"]
    out = {k: float(np.median([f[k] for f in feats])) for k in keys}
    d = [f["damping"] for f in feats if f.get("damping")]
    out["damping"] = float(np.median(d)) if d else None
    return out
