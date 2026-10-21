from flask import Blueprint, Response, jsonify, request

from .. import auth, db
from ..services import impact, simulator
from ._util import body, fail, fnum

bp = Blueprint("sim", __name__, url_prefix="/api")


# ---------------------------------------------------------------- simulator (SIMULATED data)
@bp.get("/sim/state")
@auth.require("viewer")
def sim_state():
    return jsonify(simulator.status())


@bp.post("/sim/control")
@auth.require("engineer")
def sim_control():
    d = body()
    try:
        interval = fnum(d.get("interval"), "Interval", 1, 30)
    except ValueError as e:
        return fail("invalid", str(e))
    return jsonify(simulator.control(running=d.get("running"), interval=interval))


@bp.post("/sim/scenario")
@auth.require("engineer")
def sim_scenario():
    d = body()
    if not db.one("SELECT id FROM structures WHERE id=?", (d.get("structure_id"),)):
        return fail("not_found", "Unknown structure.", 404)
    try:
        st = simulator.set_scenario(d["structure_id"], d.get("scenario"), d.get("damage"), d.get("speed"))
    except ValueError as e:
        return fail("invalid", str(e))
    db.audit(auth.current_user(), "sim.scenario", "structure", d["structure_id"], d.get("scenario"))
    return jsonify(st)


@bp.post("/sim/inject")
@auth.require("engineer")
def sim_inject():
    d = body()
    if not db.one("SELECT id FROM structures WHERE id=?", (d.get("structure_id"),)):
        return fail("not_found", "Unknown structure.", 404)
    try:
        st = simulator.inject(d["structure_id"], d.get("type"))
    except ValueError as e:
        return fail("invalid", str(e))
    db.audit(auth.current_user(), "sim.inject", "structure", d["structure_id"], d.get("type"))
    return jsonify(st)


@bp.post("/sim/step")
@auth.require("engineer")
def sim_step():
    """Fast-forward: write n simulated ticks backwards from now (useful for demos without waiting)."""
    d = body()
    sid = d.get("structure_id")
    if not db.one("SELECT id FROM structures WHERE id=?", (sid,)):
        return fail("not_found", "Unknown structure.", 404)
    n = max(1, min(int(d.get("n", 10)), 120))
    iv = simulator._state["interval"]
    now = db.now_ms()
    for i in range(n):
        simulator.tick(sid, ts_ms=now - int((n - i) * iv * 1000), dt=iv, persist_health=False)
    simulator.refresh_health(sid)
    return jsonify({"ok": True, "ticks": n})


# ---------------------------------------------------------------- Impact Lab (real rig workflow)
def _need(sid):
    if not db.one("SELECT id FROM structures WHERE id=?", (sid,)):
        return fail("not_found", "Structure not found.", 404)
    if not impact.supports(sid):
        return fail("no_rig", "Impact Lab needs a structure with three piezo channels (mode p2p).", 409)
    return None


@bp.get("/impact/<sid>/overview")
@auth.require("viewer")
def impact_overview(sid):
    e = _need(sid)
    if e:
        return e
    from .structures import _dev_out
    trials = db.q("SELECT status, COUNT(*) n FROM impact_trials WHERE structure_id=? GROUP BY status", (sid,))
    return jsonify({"devices": [_dev_out(d) for d in impact.devices(sid)], "settings": impact.get_settings(sid),
                    "baseline": impact.baseline(sid), "calibration": impact.calibration_state(sid), "live": impact.live(sid, 100),
                    "demo": simulator.p2p_status(sid), "trial_counts": {t["status"]: t["n"] for t in trials},
                    "structure": db.one("SELECT id,name,data_mode FROM structures WHERE id=?", (sid,))})


@bp.get("/impact/<sid>/live")
@auth.require("viewer")
def impact_live(sid):
    e = _need(sid)
    return e or jsonify(impact.live(sid, request.args.get("window", 100, type=int)))


@bp.get("/impact/<sid>/settings")
@auth.require("viewer")
def impact_get_settings(sid):
    e = _need(sid)
    return e or jsonify(impact.get_settings(sid))


@bp.put("/impact/<sid>/settings")
@auth.require("engineer")
def impact_put_settings(sid):
    e = _need(sid)
    if e:
        return e
    try:
        s = impact.put_settings(sid, body())
    except (ValueError, TypeError) as ex:
        return fail("invalid", str(ex))
    db.audit(auth.current_user(), "impact.settings", "structure", sid)
    return jsonify(s)


@bp.post("/impact/<sid>/demo")
@auth.require("engineer")
def impact_demo(sid):
    e = _need(sid)
    if e:
        return e
    d = body()
    try:
        return jsonify(simulator.p2p_control(sid, bool(d.get("running")), d.get("scenario", "normal"), minutes=30))
    except ValueError as ex:
        return fail("invalid", str(ex))


@bp.post("/impact/<sid>/record/start")
@auth.require("engineer")
def impact_start(sid):
    e = _need(sid)
    if e:
        return e
    d = body()
    purpose = d.get("purpose", "trial")
    cond = d.get("condition", "Intact")
    if purpose not in ("trial", "calibration") or cond not in ("Intact", "Damaged"):
        return fail("invalid", "purpose must be trial or calibration; condition must be Intact or Damaged.")
    if purpose == "calibration":
        cond = "Intact"
    st = impact.get_settings(sid)
    try:
        dur = fnum(d.get("duration"), "Duration", 1, 60, default=st["trial_duration_sec"] if purpose == "trial" else 3)
    except ValueError as ex:
        return fail("invalid", str(ex))
    return jsonify(impact.start_job(sid, purpose, cond, dur))


@bp.post("/impact/<sid>/record/finish")
@auth.require("engineer")
def impact_finish(sid):
    e = _need(sid)
    if e:
        return e
    from ..services import simulator as sim
    try:
        res = impact.finish_job(body().get("job_id"), auth.current_user())
    except ValueError as ex:
        return fail("record_failed", str(ex), 422)
    if res["purpose"] == "trial":
        sim.refresh_health(sid)
        db.audit(auth.current_user(), "impact.trial", "structure", sid, f"{res['trial']['condition']} {res['trial']['status']}")
    return jsonify(res)


@bp.get("/impact/<sid>/calibration")
@auth.require("viewer")
def impact_cal(sid):
    e = _need(sid)
    return e or jsonify(impact.calibration_state(sid))


@bp.post("/impact/<sid>/calibration/undo")
@auth.require("engineer")
def impact_cal_undo(sid):
    e = _need(sid)
    if e:
        return e
    impact.undo_calibration(sid)
    return jsonify(impact.calibration_state(sid))


@bp.delete("/impact/<sid>/calibration")
@auth.require("engineer")
def impact_cal_clear(sid):
    e = _need(sid)
    if e:
        return e
    impact.clear_calibration(sid)
    return jsonify(impact.calibration_state(sid))


@bp.post("/impact/<sid>/baseline/save")
@auth.require("engineer")
def impact_baseline_save(sid):
    e = _need(sid)
    if e:
        return e
    try:
        b = impact.save_baseline(sid, (body().get("specimen_id") or "specimen-1")[:60])
    except ValueError as ex:
        return fail("invalid", str(ex))
    from ..services import simulator as sim
    sim.refresh_health(sid)
    db.audit(auth.current_user(), "impact.baseline", "structure", sid, f"{b['num_trials']} trials, source {b['source']}")
    return jsonify(b)


@bp.get("/impact/<sid>/trials")
@auth.require("viewer")
def impact_trials(sid):
    e = _need(sid)
    return e or jsonify(impact.trials(sid, request.args.get("condition"), request.args.get("status")))


@bp.get("/impact/<sid>/trials/<tid>")
@auth.require("viewer")
def impact_trial(sid, tid):
    r = db.one("SELECT * FROM impact_trials WHERE id=? AND structure_id=?", (tid, sid))
    return jsonify(impact.trial_out(r, True)) if r else fail("not_found", "Trial not found.", 404)


@bp.delete("/impact/<sid>/trials")
@auth.require("engineer")
def impact_trials_clear(sid):
    e = _need(sid)
    if e:
        return e
    if request.args.get("confirm") != "yes":
        return fail("confirm_required", "Add ?confirm=yes to delete all trials.")
    db.run("DELETE FROM impact_trials WHERE structure_id=?", (sid,))
    db.audit(auth.current_user(), "impact.clear_trials", "structure", sid)
    from ..services import simulator as sim
    sim.refresh_health(sid)
    return jsonify({"ok": True})


@bp.delete("/impact/<sid>/trials/<tid>")
@auth.require("engineer")
def impact_trial_delete(sid, tid):
    db.run("DELETE FROM impact_trials WHERE id=? AND structure_id=?", (tid, sid))
    return jsonify({"ok": True})


@bp.get("/impact/<sid>/analysis")
@auth.require("viewer")
def impact_analysis(sid):
    e = _need(sid)
    return e or jsonify(impact.analysis(sid))


@bp.get("/impact/<sid>/export.csv")
@auth.require("viewer")
def impact_export(sid):
    e = _need(sid)
    if e:
        return e
    return Response(impact.export_csv(sid), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=structurasense_trials.csv"})
