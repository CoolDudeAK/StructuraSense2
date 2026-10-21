"""Self-benchmark of the crack detector on SYNTHETIC images with known ground truth.

Run:  python tools/eval_vision.py [N_PER_CLASS]
Writes data/vision_eval.json, which the Intelligence page shows.

This is NOT SDNET2018 and NOT field data. It checks that the code finds what it should on controlled images.
To measure real-world accuracy, run the same metrics on labelled photographs of your own structures
(or SDNET2018) -- the deck targets >=90% precision and <10% false alarms.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np  # noqa: E402

from backend import config  # noqa: E402
from backend.services import synth_images as si, vision  # noqa: E402


def run(n=30, seed=2025):
    rng = np.random.default_rng(seed)
    tp = fp = fn = tn = 0
    ratios, ious = [], []
    t0 = time.time()
    for i in range(n):
        wpx = float(rng.choice([1.6, 2.5, 3, 4, 6, 10, 14]))
        img, gt = si.make_image(np.random.default_rng(int(rng.integers(1e9))), width_px=wpx,
                                branches=int(rng.integers(1, 3)), stain=bool(rng.random() < .3))
        r, work, mask = vision.analyze(img, si.SCALE_PX_PER_MM)
        if r["crack_detected"]:
            tp += 1
            ratios.append(r["max_width_mm"] / (wpx / si.SCALE_PX_PER_MM))
            import cv2
            g = cv2.resize(gt, (mask.shape[1], mask.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
            g = cv2.dilate(g.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            m = mask > 0
            ious.append(float((g & m).sum() / max(1, (g | m).sum())))
        else:
            fn += 1
    for i in range(n):
        img, _ = si.make_image(np.random.default_rng(int(rng.integers(1e9))), width_px=None, pores=True,
                               stain=bool(rng.random() < .5))
        r, _, _ = vision.analyze(img, si.SCALE_PX_PER_MM)
        if r["crack_detected"]:
            fp += 1
        else:
            tn += 1
    out = {
        "dataset": "SYNTHETIC concrete images (not SDNET2018, not field data)",
        "method": vision.METHOD, "images_cracked": n, "images_clean": n,
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "precision": round(tp / max(1, tp + fp), 3), "recall": round(tp / max(1, tp + fn), 3),
        "false_alarm_rate": round(fp / max(1, fp + tn), 3),
        "width_ratio_median": round(float(np.median(ratios)), 3) if ratios else None,
        "mask_iou_median": round(float(np.median(ious)), 3) if ious else None,
        "targets": {"precision": 0.90, "false_alarm_rate": 0.10},
        "seconds": round(time.time() - t0, 1), "ts_ms": int(time.time() * 1000),
    }
    (config.DATA_DIR / "vision_eval.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    print(json.dumps(run(n), indent=1))
