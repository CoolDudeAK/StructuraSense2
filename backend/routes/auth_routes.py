import re

from flask import Blueprint, jsonify, request

from .. import auth, config, db
from ._util import body, fail

bp = Blueprint("auth", __name__, url_prefix="/api")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _user_out(u):
    return {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"]}


@bp.post("/auth/login")
def login():
    if not auth.throttle_login(request.remote_addr or "x"):
        return fail("rate_limited", "Too many sign-in attempts. Wait a few minutes and try again.", 429)
    d = body()
    u = db.one("SELECT * FROM users WHERE email=?", ((d.get("email") or "").strip().lower(),))
    if not u or not auth.verify_password(u["pw_hash"], d.get("password") or ""):
        return fail("bad_credentials", "Email or password is wrong.", 401)
    db.audit(u, "login")
    return jsonify({"token": auth.make_token(u), "user": _user_out(u)})


@bp.post("/auth/register")
def register():
    if not config.ALLOW_SIGNUP:
        return fail("signup_disabled", "Self sign-up is switched off. Ask an admin to create your account.", 403)
    d = body()
    email = (d.get("email") or "").strip().lower()
    name = (d.get("name") or "").strip()
    pw = d.get("password") or ""
    if not EMAIL.match(email):
        return fail("invalid_email", "Enter a valid email address.")
    if len(name) < 2:
        return fail("invalid_name", "Enter your name.")
    if len(pw) < 8:
        return fail("weak_password", "Use a password with at least 8 characters.")
    if db.one("SELECT id FROM users WHERE email=?", (email,)):
        return fail("exists", "An account with this email already exists.", 409)
    u = {"id": db.uid(), "email": email, "name": name, "role": "viewer", "pw_hash": auth.hash_password(pw), "created_ms": db.now_ms()}
    db.insert("users", u)
    return jsonify({"token": auth.make_token(u), "user": _user_out(u)}), 201


@bp.get("/auth/me")
@auth.require("viewer")
def me():
    return jsonify({"user": _user_out(auth.current_user())})


@bp.get("/users")
@auth.require("admin")
def users():
    return jsonify(db.q("SELECT id,email,name,role,created_ms FROM users ORDER BY created_ms"))


@bp.post("/users")
@auth.require("admin")
def create_user():
    d = body()
    email = (d.get("email") or "").strip().lower()
    if not EMAIL.match(email) or len(d.get("password") or "") < 8 or len((d.get("name") or "").strip()) < 2:
        return fail("invalid", "Name, a valid email and a password of 8+ characters are required.")
    if d.get("role") not in auth.RANK:
        return fail("invalid_role", "Role must be viewer, engineer or admin.")
    if db.one("SELECT id FROM users WHERE email=?", (email,)):
        return fail("exists", "An account with this email already exists.", 409)
    uid = db.uid()
    db.insert("users", {"id": uid, "email": email, "name": d["name"].strip(), "role": d["role"],
                        "pw_hash": auth.hash_password(d["password"]), "created_ms": db.now_ms()})
    db.audit(auth.current_user(), "user.create", "user", uid, email)
    return jsonify({"id": uid}), 201


@bp.patch("/users/<uid>")
@auth.require("admin")
def patch_user(uid):
    d = body()
    me_ = auth.current_user()
    if d.get("role") not in auth.RANK:
        return fail("invalid_role", "Role must be viewer, engineer or admin.")
    if uid == me_["id"] and d["role"] != "admin":
        return fail("self_demote", "You cannot remove your own admin role.")
    db.update("users", uid, {"role": d["role"]})
    db.audit(me_, "user.role", "user", uid, d["role"])
    return jsonify({"ok": True})
