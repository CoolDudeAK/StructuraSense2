import json

import cv2
import numpy as np
from flask import Blueprint, jsonify, request, send_from_directory

from .. import auth, config, db
from ..services import simulator, synth_images, vision
from ._util import body, fail, fnum

bp = Blueprint("vision", __name__, url_prefix="/api")
MAX_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 40_000_000


def _out(r, full=False):
    o = {k: r[k] for k in r if k not in ("segments_json",)}
    o["image_url"] = f"/api/files/uploads/{r['image_file']}" if r["image_file"] else None
    o["overlay_url"] = f"/api/files/uploads/{r['overlay_file']}" if r["overlay_file"] else None
    if full:
        o["segments_detail"] = json.loads(r["segments_json"] or "[]")
    return o


def _zone_ok(sid, zone):
    return (not zone) or db.one("SELECT id FROM zones WHERE id=? AND structure_id=?", (zone, sid))


def _store(sid, zone, bgr, scale, filename, origin):
    row = vision.run_and_store(sid, zone or None, bgr, scale, filename, origin=origin, user_id=auth.current_user()["id"])
    simulator.refresh_health(sid)
    return _out(db.one("SELECT * FROM crack_analyses WHERE id=?", (row["id"],)), full=True)


@bp.post("/vision/analyze")
@auth.require("engineer")
def analyze():
    f = request.files.get("image")
    sid, zone = request.form.get("structure_id"), request.form.get("zone_id") or None
    if not db.one("SELECT id FROM structures WHERE id=?", (sid,)):
        return fail("not_found", "Choose the structure this photo belongs to.", 404)
    if not _zone_ok(sid, zone):
        return fail("invalid_zone", "That zone does not belong to this structure.")
    if not f:
        return fail("no_file", "Choose a photo to analyse.")
    try:
        scale = fnum(request.form.get("scale_px_per_mm"), "Scale", 0.01, 10000)
    except ValueError as e:
        return fail("invalid", str(e))
    raw = f.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        return fail("too_large", "The photo is larger than 12 MB. Reduce its size and try again.")
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)  # decoding proves it is a real image
    if img is None:
        return fail("not_an_image", "This file is not a readable JPG or PNG image.")
    if img.shape[0] * img.shape[1] > MAX_PIXELS:
        return fail("too_large", "The image has too many pixels (limit 40 megapixels).")
    return jsonify(_store(sid, zone, img, scale, f.filename or "photo", "upload")), 201


@bp.get("/vision/samples")
@auth.require("viewer")
def samples():
    meta = synth_images.ensure_samples(config.SAMPLE_DIR)
    for m in meta:
        m["url"] = f"/api/files/samples/{m['file']}"
    return jsonify(meta)


@bp.post("/vision/samples/<name>/analyze")
@auth.require("engineer")
def analyze_sample(name):
    meta = {m["file"]: m for m in synth_images.ensure_samples(config.SAMPLE_DIR)}
    if name not in meta:
        return fail("not_found", "Unknown sample.", 404)
    d = body()
    sid, zone = d.get("structure_id"), d.get("zone_id") or None
    if not db.one("SELECT id FROM structures WHERE id=?", (sid,)) or not _zone_ok(sid, zone):
        return fail("invalid", "Choose a structure and a zone that belongs to it.")
    img = cv2.imread(str(config.SAMPLE_DIR / name))
    scale = d.get("scale_px_per_mm", meta[name]["scale_px_per_mm"])
    scale = None if scale in (None, "", 0) else float(scale)
    return jsonify(_store(sid, zone, img, scale, name, "sample")), 201


@bp.get("/vision/analyses")
@auth.require("viewer")
def list_analyses():
    sid = request.args.get("structure_id")
    rows = db.q("SELECT * FROM crack_analyses" + (" WHERE structure_id=?" if sid else "") + " ORDER BY ts_ms DESC LIMIT 60", (sid,) if sid else ())
    return jsonify([_out(r) for r in rows])


@bp.get("/vision/analyses/<aid>")
@auth.require("viewer")
def get_analysis(aid):
    r = db.one("SELECT * FROM crack_analyses WHERE id=?", (aid,))
    return jsonify(_out(r, True)) if r else fail("not_found", "Analysis not found.", 404)


@bp.delete("/vision/analyses/<aid>")
@auth.require("engineer")
def delete_analysis(aid):
    r = db.one("SELECT * FROM crack_analyses WHERE id=?", (aid,))
    if not r:
        return fail("not_found", "Analysis not found.", 404)
    db.run("DELETE FROM crack_analyses WHERE id=?", (aid,))
    for fn in (r["image_file"], r["overlay_file"]):
        if fn:
            try:
                (config.UPLOAD_DIR / fn).unlink()
            except OSError:
                pass
    db.audit(auth.current_user(), "vision.delete", "crack_analysis", aid)
    simulator.refresh_health(r["structure_id"])
    return jsonify({"ok": True})


@bp.get("/vision/detectors")
@auth.require("viewer")
def detectors():
    return jsonify(vision.detectors())


@bp.get("/files/<kind>/<path:name>")
@auth.require("viewer")
def files(kind, name):
    base = {"uploads": config.UPLOAD_DIR, "samples": config.SAMPLE_DIR}.get(kind)
    if base is None or not name.lower().endswith((".png", ".jpg", ".jpeg")):
        return fail("not_found", "File not found.", 404)
    return send_from_directory(base, name, max_age=3600)
