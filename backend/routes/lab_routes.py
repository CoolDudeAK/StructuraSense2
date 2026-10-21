"""Element Test Lab API: cubes, beams, slabs, columns - per-sensor-channel results checked against IS-code limits."""
import cv2
import numpy as np
from flask import Blueprint, Response, jsonify, request

from .. import auth, db
from ..services import elements, vision
from ._util import body, fail, fnum

bp = Blueprint("lab", __name__, url_prefix="/api/lab")
MAX_BYTES = 12 * 1024 * 1024


@bp.get("/spec")
@auth.require("viewer")
def spec():
    return jsonify(elements.spec())


@bp.get("/tests")
@auth.require("viewer")
def list_tests():
    el = request.args.get("element")
    sql, args = "SELECT * FROM element_tests", []
    if el in ("cube", "beam", "slab", "column"):
        sql += " WHERE element_type=?"
        args.append(el)
    sql += " ORDER BY ts_ms DESC LIMIT 200"
    return jsonify({"tests": [elements.out_row(r) for r in db.q(sql, args)]})


@bp.get("/tests/<tid>")
@auth.require("viewer")
def get_test(tid):
    r = db.one("SELECT * FROM element_tests WHERE id=?", (tid,))
    if not r:
        return fail("not_found", "That test was not found.", 404)
    return jsonify(elements.out_row(r, full=True))


@bp.post("/tests")
@auth.require("engineer")
def create_test():
    d = body()
    try:
        defect = fnum(d.get("defect"), "Defect level", 0, 1, default=0.0)
        seed = d.get("seed")
        res = elements.run_test(auth.current_user(), str(d.get("element_type") or ""), str(d.get("procedure") or ""), str(d.get("grade") or ""),
                                d.get("params") if isinstance(d.get("params"), dict) else {}, str(d.get("mode") or "sim"), defect,
                                d.get("metrics") if isinstance(d.get("metrics"), dict) else None,
                                d.get("channels") if isinstance(d.get("channels"), list) else None,
                                d.get("label"), d.get("notes"), str(d.get("exposure") or "normal"),
                                int(seed) if isinstance(seed, (int, float)) else None)
    except ValueError as e:
        return fail("invalid", str(e))
    db.audit(auth.current_user(), "lab_test", "element_tests", res["id"], f"{res['element_type']} {res['procedure']} {res['source']}")
    return jsonify(res), 201


@bp.delete("/tests/<tid>")
@auth.require("engineer")
def delete_test(tid):
    if not db.one("SELECT id FROM element_tests WHERE id=?", (tid,)):
        return fail("not_found", "That test was not found.", 404)
    db.run("DELETE FROM element_tests WHERE id=?", (tid,))
    return jsonify({"ok": True})


@bp.get("/cube-group")
@auth.require("viewer")
def cube_group():
    g = request.args.get("grade", "M25")
    if g not in elements.GRADES:
        return fail("invalid", "Pick a concrete grade such as M25.")
    rows = db.q("SELECT * FROM element_tests WHERE element_type='cube' AND grade=? ORDER BY ts_ms DESC LIMIT 40", (g,))
    return jsonify(elements.cube_group(g, [dict(r) for r in rows]))


@bp.post("/crack-photo")
@auth.require("engineer")
def crack_photo():
    """Measure the crack width in a real photo (needs the scale). The result can be typed into a manual test."""
    f = request.files.get("image")
    if not f:
        return fail("no_file", "Choose a photo to analyse.")
    try:
        scale = fnum(request.form.get("scale_px_per_mm"), "Scale", 0.01, 10000, required=True)
    except ValueError as e:
        return fail("invalid", str(e))
    raw = f.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        return fail("too_large", "The photo is larger than 12 MB.")
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return fail("not_an_image", "This file is not a readable JPG or PNG image.")
    res, _, _ = vision.analyze(img, scale)
    return jsonify({"crack_detected": res["crack_detected"], "max_width_mm": res["max_width_mm"], "length_mm": res["length_mm"], "severity": res["severity"],
                    "note": "Real image processing. Type max_width_mm into the Crack imaging field of a manual test."})


@bp.get("/export.csv")
@auth.require("viewer")
def export_csv():
    rows = db.q("SELECT * FROM element_tests ORDER BY ts_ms DESC LIMIT 1000")
    return Response(elements.csv_rows(rows), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=element_tests.csv"})
