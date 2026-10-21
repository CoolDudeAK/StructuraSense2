"""Authentication (JWT) and role-based access. Passwords are hashed with scrypt (werkzeug)."""
import hashlib
import hmac
import time
from functools import wraps

import jwt
from flask import g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from . import config, db

RANK = {"viewer": 1, "engineer": 2, "admin": 3}
_attempts = {}  # ip -> [timestamps], tiny login throttle for the prototype


def error(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message}}), status


def hash_password(pw):
    return generate_password_hash(pw)


def verify_password(pw_hash, pw):
    return check_password_hash(pw_hash, pw)


def make_token(user):
    now = int(time.time())
    return jwt.encode({"sub": user["id"], "role": user["role"], "name": user["name"],
                       "iat": now, "exp": now + config.TOKEN_HOURS * 3600},
                      config.SECRET_KEY, algorithm="HS256")


def _token_from_request():
    h = request.headers.get("Authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return request.args.get("token")  # EventSource / <img> / downloads cannot set headers


def current_user():
    if hasattr(g, "_user"):
        return g._user
    user = None
    tok = _token_from_request()
    if tok:
        try:
            claims = jwt.decode(tok, config.SECRET_KEY, algorithms=["HS256"])
            user = db.one("SELECT id,email,name,role FROM users WHERE id=?", (claims["sub"],))
        except jwt.PyJWTError:
            user = None
    g._user = user
    return user


def require(role="viewer"):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                return error("unauthorized", "Sign in to continue.", 401)
            if RANK[u["role"]] < RANK[role]:
                return error("forbidden", f"This action needs the {role} role. You are signed in as {u['role']}.", 403)
            return fn(*a, **kw)
        return wrapper
    return deco


def throttle_login(ip):
    now = time.time()
    lst = [t for t in _attempts.get(ip, []) if now - t < 300]
    _attempts[ip] = lst
    if len(lst) >= 20:
        return False
    lst.append(now)
    return True


# ---- device keys -------------------------------------------------------------------------
def hash_key(key: str) -> str:
    return hashlib.sha256((config.SECRET_KEY + key).encode()).hexdigest()


def device_from_key():
    """Returns the device row if a valid X-Device-Key header is present."""
    key = request.headers.get("X-Device-Key")
    if not key:
        return None
    h = hash_key(key)
    for d in db.q("SELECT * FROM devices WHERE api_key_hash IS NOT NULL"):
        if hmac.compare_digest(d["api_key_hash"], h):
            return d
    return None
