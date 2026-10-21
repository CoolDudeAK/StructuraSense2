import math

from flask import jsonify, request

from .. import auth


def body():
    d = request.get_json(silent=True)
    return d if isinstance(d, dict) else {}


def fail(code, message, status=400):
    return auth.error(code, message, status)


def fnum(v, name, lo=None, hi=None, default=None, required=False):
    """Parse a finite float with optional bounds. Raises ValueError with a user-readable message."""
    if v is None or v == "":
        if required:
            raise ValueError(f"{name} is required.")
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number.")
    if not math.isfinite(x):
        raise ValueError(f"{name} must be a finite number.")
    if lo is not None and x < lo:
        raise ValueError(f"{name} must be at least {lo}.")
    if hi is not None and x > hi:
        raise ValueError(f"{name} must be at most {hi}.")
    return x


def ok(data=None, status=200, **extra):
    out = {"ok": True}
    if data is not None:
        out["data"] = data
    out.update(extra)
    return jsonify(out), status
