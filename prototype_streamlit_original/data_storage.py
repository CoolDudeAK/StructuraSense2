"""
data_storage.py
----------------
Persistent local storage for every trial run through StructuraSense.

Uses SQLite (data/structurasense.db) so the app works completely offline
with zero external database setup, while still supporting structured
querying/filtering for the History and Analysis pages.

Also supports exporting the full trial history to CSV so the user can
open it directly in Excel.
"""

import csv
import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "structurasense.db")


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            condition TEXT NOT NULL,
            sensor1 REAL,
            sensor2 REAL,
            sensor3 REAL,
            mean_response REAL,
            max_response REAL,
            min_response REAL,
            anomaly_score REAL,
            status TEXT,
            data_source TEXT,
            notes TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def insert_trial(record: dict) -> int:
    """
    record keys expected: condition, sensor1, sensor2, sensor3,
    mean_response, max_response, min_response, anomaly_score, status,
    data_source (LIVE HARDWARE DATA / DEMO/SIMULATION DATA), notes (optional)
    """
    init_db()
    conn = _connect()
    cur = conn.execute(
        """
        INSERT INTO trials
            (timestamp, condition, sensor1, sensor2, sensor3,
             mean_response, max_response, min_response, anomaly_score,
             status, data_source, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            record.get("condition", "unknown"),
            record.get("sensor1"),
            record.get("sensor2"),
            record.get("sensor3"),
            record.get("mean_response"),
            record.get("max_response"),
            record.get("min_response"),
            record.get("anomaly_score"),
            record.get("status"),
            record.get("data_source", "LIVE HARDWARE DATA"),
            record.get("notes", ""),
        ),
    )
    conn.commit()
    trial_id = cur.lastrowid
    conn.close()
    return trial_id


def get_all_trials(condition_filter=None, status_filter=None) -> list:
    init_db()
    conn = _connect()
    query = "SELECT * FROM trials"
    clauses, params = [], []
    if condition_filter and condition_filter != "All":
        clauses.append("condition = ?")
        params.append(condition_filter)
    if status_filter and status_filter != "All":
        clauses.append("status = ?")
        params.append(status_filter)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_all_trials():
    init_db()
    conn = _connect()
    conn.execute("DELETE FROM trials")
    conn.commit()
    conn.close()


def export_csv(path: str) -> str:
    trials = get_all_trials()
    fieldnames = [
        "id", "timestamp", "condition", "sensor1", "sensor2", "sensor3",
        "mean_response", "max_response", "min_response", "anomaly_score",
        "status", "data_source", "notes",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for t in trials:
            writer.writerow({k: t.get(k, "") for k in fieldnames})
    return path
