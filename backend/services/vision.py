"""Crack detection from a photo.

REAL implementation, but CLASSICAL computer vision (not a trained neural network):
  1. grayscale + flat-field correction (removes lighting gradients and shadows)
  2. multi-scale Sato ridge filter tuned for dark, thin, line-like structures
  3. hysteresis threshold -> candidate regions
  4. shape filter (long and thin, not round pores or blotches)
  5. per-crack width measured at half the local contrast depth (FWHM) along the skeleton
  6. widths converted to millimetres only when the user supplies a scale (pixels per mm)

SLOT: a CNN/YOLO detector (as in the pitch deck) can plug in via `DETECTORS`. The ONNX path needs a trained
weights file (models/crack_yolo.onnx) that this prototype does not ship, so it reports itself as unavailable.
"""
import cv2
import numpy as np
from skimage.filters import apply_hysteresis_threshold, sato
from skimage.measure import label as sk_label
from skimage.morphology import skeletonize

from .. import config

METHOD = "opencv-ridge-v1"
LO, HI = 0.030, 0.060         # ridge response thresholds on flat-fielded image
MIN_LEN_FRAC = 0.06          # min skeleton length as fraction of the long image side
MIN_ASPECT = 8.0              # length / mean width


def detectors():
    onnx = config.MODEL_DIR / "crack_yolo.onnx"
    return [
        {"id": METHOD, "name": "Classical ridge detector (OpenCV + scikit-image)", "status": "REAL", "available": True,
         "note": "Not a trained model. Tuned on a synthetic benchmark; needs field validation."},
        {"id": "yolo-onnx", "name": "YOLO / CNN crack detector", "status": "SLOT", "available": False,
         "note": ("Weights found but loader not implemented." if onnx.exists() else
                  "Needs trained weights at data/models/crack_yolo.onnx (e.g. trained on SDNET2018). Not included.")},
    ]


def _severity(width_mm, area_pct, calibrated, detected):
    if not detected:
        return "none"
    if calibrated and width_mm is not None:
        for lim, name in ((0.1, "hairline"), (0.3, "fine"), (1.0, "moderate"), (3.0, "wide")):
            if width_mm < lim:
                return name
        return "very wide"
    return "minor (uncalibrated)" if area_pct < 0.5 else ("moderate (uncalibrated)" if area_pct < 3 else "extensive (uncalibrated)")


def _sk_length(sk):
    return float(sk.sum()) * 1.1  # 8-connected skeleton: ~10% longer than pixel count on average


def analyze(bgr, scale_px_per_mm=None, max_side=1200):
    h0, w0 = bgr.shape[:2]
    f = min(1.0, max_side / max(h0, w0))
    img = cv2.resize(bgr, (int(w0 * f), int(h0 * f)), interpolation=cv2.INTER_AREA) if f < 1 else bgr.copy()
    h, w = img.shape[:2]
    scale = (scale_px_per_mm * f) if scale_px_per_mm else None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    illum = cv2.GaussianBlur(gray, (0, 0), max(h, w) / 14.0)
    norm = gray / (illum + 1.0)
    resp = sato(norm, sigmas=(1.0, 1.6, 2.5, 4.0), black_ridges=True)
    cand = apply_hysteresis_threshold(resp, LO, HI)
    cand = cv2.morphologyEx(cand.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    lab = sk_label(cand, connectivity=2)
    smooth = cv2.GaussianBlur(norm, (0, 0), 0.8)
    depth_map = np.clip(1.0 - smooth, 0, 1)

    final = np.zeros((h, w), np.uint8)
    segs = []
    min_len = MIN_LEN_FRAC * max(h, w)
    for rid in range(1, lab.max() + 1):
        comp = (lab == rid)
        area = int(comp.sum())
        if area < 25:
            continue
        sk = skeletonize(comp)
        L = _sk_length(sk)
        if L < min_len:
            continue
        mean_w = area / max(L, 1.0)
        if L / max(mean_w, 1e-6) < MIN_ASPECT:
            continue
        ys, xs = np.nonzero(sk)
        depth = float(np.percentile(depth_map[ys, xs], 90))
        strength = float(resp[ys, xs].mean())
        if depth < 0.15 or strength < 0.07:
            continue
        near = cv2.dilate(comp.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        refined = near & (depth_map > 0.5 * depth)
        refined = cv2.morphologyEx(refined.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) if refined.sum() > 80 else refined.astype(np.uint8)
        refined |= (sk.astype(np.uint8))
        dt = cv2.distanceTransform(refined, cv2.DIST_L2, 3)
        widths = np.maximum(1.0, 2 * dt[ys, xs] - 1.0)  # distance transform counts to the first background pixel
        wmax = float(np.percentile(widths, 95))
        wmean = float(widths.mean())
        x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        final |= refined
        segs.append({"bbox": [x0, y0, x1, y1], "length_px": round(L, 1), "max_width_px": round(wmax, 2),
                     "mean_width_px": round(wmean, 2), "area_px": int(refined.sum()),
                     "strength": round(strength, 4), "depth": round(depth, 3)})
    segs.sort(key=lambda s: -s["length_px"])
    for i, s in enumerate(segs, 1):
        s["id"] = i
        s["length_mm"] = round(s["length_px"] / scale, 2) if scale else None
        s["max_width_mm"] = round(s["max_width_px"] / scale, 3) if scale else None
    detected = bool(segs)
    area_pct = float(final.sum()) / (h * w) * 100
    total_len = sum(s["length_px"] for s in segs)
    max_w = max((s["max_width_px"] for s in segs), default=0.0)
    mean_w = (sum(s["mean_width_px"] * s["length_px"] for s in segs) / total_len) if total_len else 0.0
    max_w_mm = round(max_w / scale, 3) if (scale and detected) else None
    result = {
        "img_w": w0, "img_h": h0, "work_w": w, "work_h": h, "scale_px_per_mm": scale_px_per_mm,
        "crack_detected": detected, "segments": len(segs), "crack_area_pct": round(area_pct, 3),
        "length_px": round(total_len / f, 1), "max_width_px": round(max_w / f, 2), "mean_width_px": round(mean_w / f, 2),
        "length_mm": round(total_len / scale, 1) if (scale and detected) else None,
        "max_width_mm": max_w_mm,
        "mean_width_mm": round(mean_w / scale, 3) if (scale and detected) else None,
        "severity": _severity(max_w_mm, area_pct, bool(scale), detected),
        "ridge_strength": round(float(np.mean([s["strength"] for s in segs])), 4) if segs else 0.0,
        "method": METHOD, "segments_detail": segs,
    }
    return result, img, final


def overlay(img, mask, segs):
    out = img.copy()
    red = np.zeros_like(out)
    red[:, :] = (40, 40, 230)
    m = mask.astype(bool)
    out[m] = (0.35 * out[m] + 0.65 * red[m]).astype(np.uint8)
    for s in segs:
        x0, y0, x1, y1 = s["bbox"]
        pad = 10
        cv2.rectangle(out, (max(0, x0 - pad), max(0, y0 - pad)), (x1 + pad, y1 + pad), (0, 190, 255), 2, cv2.LINE_AA)
        lab = f"#{s['id']}  " + (f"{s['max_width_mm']:.2f} mm" if s.get("max_width_mm") is not None else f"{s['max_width_px']:.1f} px")
        (tw, th), _ = cv2.getTextSize(lab, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        ty = max(th + 6, y0 - pad - 4)
        cv2.rectangle(out, (max(0, x0 - pad), ty - th - 6), (max(0, x0 - pad) + tw + 10, ty + 4), (0, 190, 255), -1)
        cv2.putText(out, lab, (max(0, x0 - pad) + 5, ty - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 2, cv2.LINE_AA)
    return out


def run_and_store(structure_id, zone_id, bgr, scale_px_per_mm, filename, origin="upload", user_id=None, ts_ms=None):
    """Analyse an image, save original + overlay, store the result, queue cloud sync. Returns the DB row (+urls)."""
    import json

    from .. import db
    from . import cloud_sync
    res, work, mask = analyze(bgr, scale_px_per_mm)
    aid = db.uid()
    orig_name, over_name = f"{aid}_orig.jpg", f"{aid}_overlay.png"
    cv2.imwrite(str(config.UPLOAD_DIR / orig_name), work, [cv2.IMWRITE_JPEG_QUALITY, 88])
    cv2.imwrite(str(config.UPLOAD_DIR / over_name), overlay(work, mask, res["segments_detail"]))
    row = {"id": aid, "structure_id": structure_id, "zone_id": zone_id, "ts_ms": ts_ms or db.now_ms(), "filename": filename,
           "image_file": orig_name, "overlay_file": over_name, "img_w": res["img_w"], "img_h": res["img_h"],
           "scale_px_per_mm": scale_px_per_mm, "crack_area_pct": res["crack_area_pct"], "length_px": res["length_px"],
           "max_width_px": res["max_width_px"], "mean_width_px": res["mean_width_px"], "length_mm": res["length_mm"],
           "max_width_mm": res["max_width_mm"], "mean_width_mm": res["mean_width_mm"], "segments": res["segments"],
           "severity": res["severity"], "crack_detected": 1 if res["crack_detected"] else 0, "method": res["method"],
           "ridge_strength": res["ridge_strength"], "segments_json": json.dumps(res["segments_detail"]),
           "origin": origin, "user_id": user_id}
    db.insert("crack_analyses", row)
    cloud_sync.enqueue("crack_analyses", aid)
    return row
