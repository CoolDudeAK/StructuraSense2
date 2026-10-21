"""Cloud mirror (Supabase / PostgREST). Local SQLite stays the system of record; changed rows are queued
and pushed to Supabase with upserts. The service key is read on the server only and is never sent to the browser.

STATUS: REQUIRES EXTERNAL SERVICE. Verified against a local mock of the PostgREST API in tests/test_api.py;
not verified against a live Supabase project (needs your credentials). Firebase is a FUTURE adapter (see CloudProvider).
"""
import json
import threading
import time

import requests

from .. import config, db

# local table -> (cloud table, columns to send). Raw high-volume readings and waveform samples are NOT mirrored.
TABLES = {
    "structures": ["id", "name", "kind", "location", "state", "lat", "lon", "built_year", "material", "span_m",
                   "owner_agency", "description", "is_demo", "data_mode", "limits_json", "created_ms"],
    "zones": ["id", "structure_id", "idx", "name", "x0", "x1"],
    "devices": ["id", "structure_id", "zone_id", "name", "kind", "channel", "unit", "source_type", "pos_x", "pos_y",
                "fs", "config_json", "last_seen_ms", "created_ms"],
    "health_scores": ["id", "structure_id", "ts_ms", "score", "band", "coverage", "components_json", "zones_json",
                      "method", "data_mode"],
    "alerts": ["id", "structure_id", "zone_id", "device_id", "ts_ms", "severity", "kind", "title", "message", "value",
               "threshold", "status", "origin", "dedupe_key", "ack_by", "ack_ms", "resolved_by", "resolved_ms",
               "resolution_note"],
    "crack_analyses": ["id", "structure_id", "zone_id", "ts_ms", "filename", "img_w", "img_h", "scale_px_per_mm",
                       "crack_area_pct", "length_px", "max_width_px", "mean_width_px", "length_mm", "max_width_mm",
                       "mean_width_mm", "segments", "severity", "crack_detected", "method", "ridge_strength", "origin"],
    "maintenance_tasks": ["id", "structure_id", "zone_id", "created_ms", "title", "description", "priority", "status",
                          "due_date", "est_cost_inr", "origin_alert_id", "proposed_by", "signed_off_by", "signed_off_ms"],
    "waveforms": ["id", "device_id", "structure_id", "ts_ms", "fs", "n", "source", "rms", "peak", "crest", "kurtosis",
                  "dom_freq", "centroid", "damping", "bands_json", "is_baseline", "label", "notes"],
}
PUSH_ORDER = ["structures", "zones", "devices", "health_scores", "alerts", "crack_analyses", "maintenance_tasks", "waveforms"]

_state = {"last_ok_ms": None, "last_error": None, "pushed": 0}
_stop = threading.Event()


class CloudProvider:
    """Adapter contract. Add a FirebaseProvider here later without touching the rest of the app."""
    name = "none"

    def configured(self):
        return False

    def upsert(self, table, rows):
        raise NotImplementedError

    def ping(self):
        raise NotImplementedError


class SupabaseProvider(CloudProvider):
    name = "supabase"

    def __init__(self, url, key):
        self.url, self.key = url.rstrip("/"), key

    def configured(self):
        return bool(self.url and self.key)

    def _h(self, extra=None):
        h = {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        h.update(extra or {})
        return h

    def upsert(self, table, rows):
        r = requests.post(f"{self.url}/rest/v1/{table}?on_conflict=id", data=json.dumps(rows, default=str),
                          headers=self._h({"Prefer": "resolution=merge-duplicates,return=minimal"}), timeout=20)
        if r.status_code >= 300:
            raise RuntimeError(f"{table}: HTTP {r.status_code} {r.text[:200]}")

    def ping(self):
        r = requests.get(f"{self.url}/rest/v1/structures?select=id&limit=1", headers=self._h(), timeout=10)
        if r.status_code >= 300:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        return True


class FirebaseProvider(CloudProvider):
    name = "firebase"  # FUTURE: Firestore adapter not implemented in this prototype


def get_provider():
    url = db.get_setting("cloud.url") or config.SUPABASE_URL
    key = db.get_setting("cloud.key") or config.SUPABASE_SERVICE_KEY
    p = SupabaseProvider(url or "", key or "")
    return p if p.configured() else CloudProvider()


def status():
    p = get_provider()
    pend = db.one("SELECT COUNT(*) n FROM sync_queue WHERE status='pending'")["n"]
    failed = db.one("SELECT COUNT(*) n FROM sync_queue WHERE status='failed'")["n"]
    return {"provider": p.name, "configured": p.configured(),
            "url": (p.url if p.configured() else None),
            "key_set": p.configured(), "pending": pend, "failed": failed,
            "last_ok_ms": _state["last_ok_ms"], "last_error": _state["last_error"], "total_pushed": _state["pushed"],
            "source": "settings" if db.get_setting("cloud.url") else ("environment" if config.SUPABASE_URL else "none")}


def enqueue(table, row_id):
    if not get_provider().configured():
        return
    db.run("INSERT OR IGNORE INTO sync_queue(table_name,row_id,created_ms,status) VALUES(?,?,?, 'pending')",
           (table, row_id, db.now_ms()))


def enqueue_all():
    n = 0
    for t in PUSH_ORDER:
        for r in db.q(f"SELECT id FROM {t}"):
            enqueue(t, r["id"])
            n += 1
    return n


def flush(max_rows=500):
    """Push queued rows. Returns a summary dict; never raises."""
    p = get_provider()
    if not p.configured():
        return {"ok": False, "message": "Cloud sync is not configured."}
    pushed, errors = 0, []
    try:
        for t in PUSH_ORDER:
            q = db.q("SELECT id,row_id,attempts FROM sync_queue WHERE status='pending' AND table_name=? LIMIT ?", (t, max_rows))
            if not q:
                continue
            cols = TABLES[t]
            rows, ids = [], []
            for it in q:
                r = db.one(f"SELECT {','.join(cols)} FROM {t} WHERE id=?", (it["row_id"],))
                if r is not None:
                    rows.append(r)
                ids.append(it["id"])
            try:
                for i in range(0, len(rows), 100):
                    p.upsert(t, rows[i:i + 100])
                db.run(f"DELETE FROM sync_queue WHERE id IN ({','.join('?' for _ in ids)})", ids)
                pushed += len(rows)
            except Exception as e:  # keep going with other tables
                errors.append(str(e))
                for it in q:
                    if it["attempts"] + 1 >= 5:
                        db.run("DELETE FROM sync_queue WHERE id=?", (it["id"],))
                        db.run("INSERT OR REPLACE INTO sync_queue(table_name,row_id,created_ms,status,attempts,last_error) VALUES(?,?,?,'failed',?,?)",
                               (t, it["row_id"], db.now_ms(), it["attempts"] + 1, str(e)[:300]))
                    else:
                        db.run("UPDATE sync_queue SET attempts=attempts+1,last_error=? WHERE id=?", (str(e)[:300], it["id"]))
    except Exception as e:
        errors.append(str(e))
    if pushed:
        _state["pushed"] += pushed
    if errors:
        _state["last_error"] = errors[0]
    else:
        _state["last_error"] = None
        _state["last_ok_ms"] = db.now_ms()
    return {"ok": not errors, "pushed": pushed, "errors": errors}


def test_connection():
    p = get_provider()
    if not p.configured():
        return {"ok": False, "message": "Add your Supabase project URL and service key first."}
    try:
        p.ping()
        return {"ok": True, "message": "Connected. The 'structures' table is reachable."}
    except Exception as e:
        return {"ok": False, "message": f"Could not reach Supabase: {e}"}


def start_worker():
    def loop():
        while not _stop.wait(config.CLOUD_SYNC_INTERVAL_S):
            try:
                if get_provider().configured():
                    flush()
            except Exception as e:
                _state["last_error"] = str(e)
    threading.Thread(target=loop, name="cloud-sync", daemon=True).start()
