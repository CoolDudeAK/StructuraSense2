from flask import Blueprint, jsonify

from .. import auth, db
from ..services import cloud_sync
from ._util import body, fail

bp = Blueprint("cloud", __name__, url_prefix="/api/cloud")


@bp.get("/status")
@auth.require("viewer")
def status():
    return jsonify(cloud_sync.status())


@bp.put("/config")
@auth.require("admin")
def put_config():
    d = body()
    url = (d.get("url") or "").strip().rstrip("/")
    key = (d.get("key") or "").strip()
    if not url.startswith("https://") or len(key) < 20:
        return fail("invalid", "Enter your Supabase project URL (https://...) and the service-role key.")
    db.set_setting("cloud.url", url)
    db.set_setting("cloud.key", key)
    db.audit(auth.current_user(), "cloud.configure", "cloud", None, url)
    return jsonify(cloud_sync.status())


@bp.delete("/config")
@auth.require("admin")
def clear_config():
    db.run("DELETE FROM settings WHERE key IN ('cloud.url','cloud.key')")
    db.audit(auth.current_user(), "cloud.clear", "cloud")
    return jsonify(cloud_sync.status())


@bp.post("/test")
@auth.require("admin")
def test():
    return jsonify(cloud_sync.test_connection())


@bp.post("/sync-now")
@auth.require("admin")
def sync_now():
    return jsonify(cloud_sync.flush())


@bp.post("/push-all")
@auth.require("admin")
def push_all():
    n = cloud_sync.enqueue_all()
    return jsonify({"queued": n, **cloud_sync.flush()})
