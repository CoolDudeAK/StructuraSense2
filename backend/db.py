"""SQLite access layer: one connection per thread, small helpers."""
import json
import re
import sqlite3
import threading
import time
import uuid

from . import config

_local = threading.local()
_write_lock = threading.RLock()


def now_ms() -> int:
    return int(time.time() * 1000)


def uid() -> str:
    return uuid.uuid4().hex


def conn() -> sqlite3.Connection:
    c = getattr(_local, "c", None)
    if c is None or getattr(_local, "path", None) != str(config.DB_PATH):
        c = sqlite3.connect(str(config.DB_PATH), timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA synchronous=NORMAL")
        _local.c = c
        _local.path = str(config.DB_PATH)
    return c


def init_db():
    with _write_lock:
        c = conn()
        c.executescript(config.SCHEMA_PATH.read_text(encoding="utf-8"))
        c.commit()
        _migrate(c)


def _migrate(c):
    """Upgrade databases created by an earlier version (SQLite cannot alter a CHECK constraint in place)."""
    row = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='devices'").fetchone()
    if row and "rf_coil" not in row[0]:
        schema = config.SCHEMA_PATH.read_text(encoding="utf-8")
        m = re.search(r"CREATE TABLE IF NOT EXISTS devices \(.*?\n\);", schema, re.S)
        new_sql = m.group(0).replace("CREATE TABLE IF NOT EXISTS devices (", "CREATE TABLE devices_new (", 1)
        c.commit()
        c.execute("PRAGMA foreign_keys=OFF")
        try:
            c.execute("BEGIN")
            c.execute(new_sql)
            c.execute("INSERT INTO devices_new SELECT * FROM devices")
            c.execute("DROP TABLE devices")
            c.execute("ALTER TABLE devices_new RENAME TO devices")
            c.execute("CREATE INDEX IF NOT EXISTS idx_devices_structure ON devices(structure_id)")
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        finally:
            c.execute("PRAGMA foreign_keys=ON")


def q(sql, args=()):
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def one(sql, args=()):
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def run(sql, args=()):
    with _write_lock:
        c = conn()
        cur = c.execute(sql, args)
        c.commit()
        return cur


def run_many(sql, rows):
    with _write_lock:
        c = conn()
        c.executemany(sql, rows)
        c.commit()


def insert(table, row: dict):
    cols = ",".join(row.keys())
    ph = ",".join("?" for _ in row)
    with _write_lock:
        c = conn()
        c.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph})", list(row.values()))
        c.commit()


def update(table, row_id, fields: dict, key="id"):
    if not fields:
        return
    sets = ",".join(f"{k}=?" for k in fields)
    with _write_lock:
        c = conn()
        c.execute(f"UPDATE {table} SET {sets} WHERE {key}=?", list(fields.values()) + [row_id])
        c.commit()


def get_setting(key, default=None):
    r = one("SELECT value FROM settings WHERE key=?", (key,))
    if r is None:
        return default
    try:
        return json.loads(r["value"])
    except (TypeError, ValueError):
        return r["value"]


def set_setting(key, value):
    run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)))


def audit(user, action, entity=None, entity_id=None, detail=None):
    run("INSERT INTO audit_log(ts_ms,user_id,user_name,action,entity,entity_id,detail) VALUES(?,?,?,?,?,?,?)",
        (now_ms(), (user or {}).get("id"), (user or {}).get("name", "system"), action, entity, entity_id,
         detail if isinstance(detail, str) or detail is None else json.dumps(detail)))
