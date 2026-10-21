"""Synthetic concrete-surface images with known crack ground truth.
Used for (1) the "Try a sample" images in the UI, (2) the self-benchmark of the crack detector, (3) tests.
These are SYNTHETIC. They are not SDNET2018 photographs and say nothing about real-world accuracy."""
import cv2
import numpy as np

SCALE_PX_PER_MM = 10.0  # all synthetic scenes: 1200 px == 120 mm


def _noise(h, w, sigma, amp, rng):
    n = rng.normal(0, 1, (h, w)).astype(np.float32)
    n = cv2.GaussianBlur(n, (0, 0), sigma)
    return n / (n.std() + 1e-9) * amp


def concrete(h, w, rng, pores=True, stain=False, gradient=True):
    base = np.full((h, w), 148.0, np.float32)
    base += _noise(h, w, 1.0, 3.5, rng) + _noise(h, w, 4.0, 5.0, rng) + _noise(h, w, 20.0, 7.0, rng)
    if gradient:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        a = rng.uniform(0, 2 * np.pi)
        base += (np.cos(a) * xx / w + np.sin(a) * yy / h) * rng.uniform(8, 18)
    if pores:
        for _ in range(int(rng.integers(25, 60))):
            x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
            r = int(rng.integers(2, 6))
            cv2.circle(base, (x, y), r, float(rng.uniform(70, 105)), -1, cv2.LINE_AA)
    if stain:
        m = np.zeros((h, w), np.float32)
        for _ in range(int(rng.integers(1, 4))):
            cv2.ellipse(m, (int(rng.integers(0, w)), int(rng.integers(0, h))),
                        (int(rng.integers(80, 260)), int(rng.integers(40, 160))), float(rng.uniform(0, 180)), 0, 360, 1.0, -1)
        m = cv2.GaussianBlur(m, (0, 0), 25)
        base -= m * rng.uniform(18, 35)
    return base


def draw_crack(img, rng, width_px=4.0, branches=1):
    """Random-walk crack from one edge to the opposite one. Returns the ground-truth mask."""
    h, w = img.shape
    gt = np.zeros((h, w), np.uint8)
    horizontal = rng.random() < 0.5
    pts = []
    if horizontal:
        x, y, ang = 0.0, float(rng.uniform(0.25 * h, 0.75 * h)), float(rng.normal(0, 0.25))
        while x < w:
            pts.append((x, y))
            ang += rng.normal(0, 0.28)
            ang = float(np.clip(ang, -1.0, 1.0))
            x += 14 * np.cos(ang)
            y += 14 * np.sin(ang)
    else:
        x, y, ang = float(rng.uniform(0.25 * w, 0.75 * w)), 0.0, float(rng.normal(0, 0.25))
        while y < h:
            pts.append((x, y))
            ang += rng.normal(0, 0.28)
            ang = float(np.clip(ang, -1.0, 1.0))
            y += 14 * np.cos(ang)
            x += 14 * np.sin(ang)
    paths = [pts]
    for _ in range(branches - 1):
        i = int(rng.integers(len(pts) // 4, 3 * len(pts) // 4))
        bx, by = pts[i]
        a = float(rng.uniform(0.5, 1.1)) * (1 if rng.random() < 0.5 else -1)
        seg = [(bx, by)]
        for _ in range(int(rng.integers(8, 18))):
            a += rng.normal(0, 0.25)
            bx += 12 * np.cos(a if horizontal else np.pi / 2 - a)
            by += 12 * np.sin(a if horizontal else np.pi / 2 - a)
            seg.append((bx, by))
        paths.append(seg)
    layer = np.zeros((h, w), np.float32)
    for pi, path in enumerate(paths):
        wscale = 1.0 if pi == 0 else 0.6
        for i in range(len(path) - 1):
            t = i / max(1, len(path) - 1)
            wd = max(1.0, width_px * wscale * (0.8 + 0.4 * np.sin(3 * t * np.pi + pi)))
            p1 = (int(path[i][0] * 16), int(path[i][1] * 16))
            p2 = (int(path[i + 1][0] * 16), int(path[i + 1][1] * 16))
            cv2.line(layer, p1, p2, 1.0, max(1, int(round(wd))), cv2.LINE_AA, shift=4)
            cv2.line(gt, (int(path[i][0]), int(path[i][1])), (int(path[i + 1][0]), int(path[i + 1][1])), 255,
                     max(1, int(round(wd))), cv2.LINE_8)
    layer = cv2.GaussianBlur(layer, (0, 0), 0.7)
    depth = float(rng.uniform(70, 95))
    img -= layer * depth
    return gt


def make_image(rng, width_px=None, w=1200, h=800, pores=True, stain=False, branches=1):
    """Returns (bgr_uint8, gt_mask_uint8 or zeros). width_px=None -> no crack."""
    g = concrete(h, w, rng, pores=pores, stain=stain)
    gt = np.zeros((h, w), np.uint8)
    if width_px:
        gt = draw_crack(g, rng, width_px=width_px, branches=branches)
    g += _noise(h, w, 0.8, 2.0, rng)  # sensor noise
    g = np.clip(g, 0, 255).astype(np.uint8)
    bgr = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    return bgr, gt


SAMPLES = [
    # filename, label, width_px, kwargs, seed, caption
    ("sample_hairline.png", "Hairline crack", 1.6, dict(), 101, "Expected: about 0.1-0.2 mm"),
    ("sample_fine.png", "Fine crack", 3.0, dict(branches=2), 102, "Expected: about 0.3 mm"),
    ("sample_moderate.png", "Moderate crack", 6.0, dict(branches=2), 103, "Expected: about 0.6 mm"),
    ("sample_wide.png", "Wide crack", 14.0, dict(branches=2), 104, "Expected: about 1.4 mm"),
    ("sample_clean_pores.png", "Clean surface with pores", None, dict(pores=True), 105, "Expected: no crack"),
    ("sample_clean_stained.png", "Clean surface with stains", None, dict(stain=True), 106, "Expected: no crack"),
]


def ensure_samples(directory):
    import json
    directory.mkdir(parents=True, exist_ok=True)
    meta = []
    for fn, label, wpx, kw, seed, cap in SAMPLES:
        p = directory / fn
        if not p.exists():
            img, _ = make_image(np.random.default_rng(seed), width_px=wpx, **kw)
            cv2.imwrite(str(p), img)
        meta.append({"file": fn, "label": label, "caption": cap, "scale_px_per_mm": SCALE_PX_PER_MM,
                     "true_width_mm": (wpx / SCALE_PX_PER_MM if wpx else None), "has_crack": bool(wpx)})
    (directory / "samples.json").write_text(json.dumps(meta, indent=1))
    return meta
