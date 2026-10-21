import time

from flask import Blueprint, jsonify, request

from .. import auth, db, events
from ..services import alerts_engine, cloud_sync, simulator
from ._util import body, fail

bp = Blueprint("alerts", __name__, url_prefix="/api")


@bp.get("/alerts")
@auth.require("viewer")
def list_alerts():
    sql, args = "SELECT a.*, s.name AS structure_name, z.name AS zone_name FROM alerts a JOIN structures s ON s.id=a.structure_id LEFT JOIN zones z ON z.id=a.zone_id WHERE 1=1", []
    st = request.args.get("status")
    if st == "active":
        sql += " AND a.status IN ('open','acknowledged')"
    elif st:
        sql += " AND a.status=?"
        args.append(st)
    if request.args.get("structure_id"):
        sql += " AND a.structure_id=?"
        args.append(request.args["structure_id"])
    if request.args.get("severity"):
        sql += " AND a.severity=?"
        args.append(request.args["severity"])
    sql += " ORDER BY CASE a.status WHEN 'open' THEN 0 WHEN 'acknowledged' THEN 1 ELSE 2 END, CASE a.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, a.ts_ms DESC LIMIT ?"
    args.append(min(request.args.get("limit", 100, type=int), 500))
    return jsonify(db.q(sql, args))


def _transition(aid, new, note=None):
    a = db.one("SELECT * FROM alerts WHERE id=?", (aid,))
    if not a:
        return fail("not_found", "Alert not found.", 404)
    u = auth.current_user()
    now = db.now_ms()
    f = {"status": new}
    if new == "acknowledged":
        if a["status"] != "open":
            return fail("bad_state", "Only open alerts can be acknowledged.", 409)
        f.update(ack_by=u["name"], ack_ms=now)
    elif new in ("resolved", "dismissed"):
        if a["status"] not in ("open", "acknowledged"):
            return fail("bad_state", "This alert is already closed.", 409)
        if new == "resolved" and not (note or "").strip():
            return fail("note_required", "Write a short note on what was checked or done. It becomes part of the record.")
        f.update(resolved_by=u["name"], resolved_ms=now, resolution_note=(note or "").strip()[:500] or None)
        if a["status"] == "open":
            f.update(ack_by=u["name"], ack_ms=now)
    db.update("alerts", aid, f)
    cloud_sync.enqueue("alerts", aid)
    db.audit(u, f"alert.{new}", "alert", aid, note)
    events.publish("alert_update", {"id": aid, "status": new, "structure_id": a["structure_id"]})
    return jsonify({"ok": True, "status": new})


@bp.post("/alerts/<aid>/ack")
@auth.require("engineer")
def ack(aid):
    return _transition(aid, "acknowledged")


@bp.post("/alerts/<aid>/resolve")
@auth.require("engineer")
def resolve(aid):
    return _transition(aid, "resolved", body().get("note"))


@bp.post("/alerts/<aid>/dismiss")
@auth.require("engineer")
def dismiss(aid):
    return _transition(aid, "dismissed", body().get("note"))


@bp.get("/maintenance")
@auth.require("viewer")
def maintenance():
    sql, args = "SELECT m.*, s.name AS structure_name, z.name AS zone_name FROM maintenance_tasks m JOIN structures s ON s.id=m.structure_id LEFT JOIN zones z ON z.id=m.zone_id WHERE 1=1", []
    if request.args.get("structure_id"):
        sql += " AND m.structure_id=?"
        args.append(request.args["structure_id"])
    if request.args.get("status") == "active":
        sql += " AND m.status IN ('proposed','approved','in_progress')"
    sql += " ORDER BY m.priority, m.created_ms DESC LIMIT 200"
    return jsonify(db.q(sql, args))


@bp.post("/maintenance")
@auth.require("engineer")
def create_task():
    d = body()
    if not db.one("SELECT id FROM structures WHERE id=?", (d.get("structure_id"),)):
        return fail("not_found", "Choose a structure.", 404)
    if len((d.get("title") or "").strip()) < 3 or d.get("priority") not in ("P1", "P2", "P3"):
        return fail("invalid", "A title and a priority (P1, P2 or P3) are required.")
    tid = db.uid()
    u = auth.current_user()
    db.insert("maintenance_tasks", {"id": tid, "structure_id": d["structure_id"], "zone_id": d.get("zone_id") or None, "created_ms": db.now_ms(),
                                    "title": d["title"].strip()[:120], "description": (d.get("description") or "")[:800], "priority": d["priority"],
                                    "status": "approved", "due_date": d.get("due_date"), "est_cost_inr": d.get("est_cost_inr"),
                                    "proposed_by": u["name"], "signed_off_by": u["name"], "signed_off_ms": db.now_ms()})
    cloud_sync.enqueue("maintenance_tasks", tid)
    return jsonify({"id": tid}), 201


@bp.patch("/maintenance/<tid>")
@auth.require("engineer")
def patch_task(tid):
    t = db.one("SELECT * FROM maintenance_tasks WHERE id=?", (tid,))
    if not t:
        return fail("not_found", "Task not found.", 404)
    d = body()
    new = d.get("status")
    allowed = {"proposed": ("approved", "rejected"), "approved": ("in_progress", "done", "rejected"), "in_progress": ("done",),
               "done": (), "rejected": ("proposed",)}
    if new not in allowed[t["status"]]:
        return fail("bad_state", f"A {t['status']} task cannot move to {new}.", 409)
    u = auth.current_user()
    f = {"status": new}
    if new in ("approved", "rejected", "done"):
        f.update(signed_off_by=u["name"], signed_off_ms=db.now_ms())
    if d.get("due_date"):
        f["due_date"] = str(d["due_date"])[:10]
    db.update("maintenance_tasks", tid, f)
    cloud_sync.enqueue("maintenance_tasks", tid)
    db.audit(u, f"maintenance.{new}", "task", tid)
    return jsonify({"ok": True, "status": new})
