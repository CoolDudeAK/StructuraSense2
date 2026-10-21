"""
config.py
---------
Handles loading and saving of user-configurable application settings.

Settings are stored locally in data/settings.json so the app works fully
offline and remembers the user's preferences between runs.
"""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

DEFAULT_SETTINGS = {
    # --- Serial ---
    "com_port": "",
    "baud_rate": 115200,

    # --- Experiment ---
    "trial_duration_sec": 5,
    "sampling_interval_sec": 0.1,
    "num_baseline_trials": 20,

    # --- Detection ---
    # Two configurable bands, expressed as combined deviation % from baseline.
    # combined_score <= anomaly_threshold_pct         -> NORMAL
    # anomaly_threshold_pct < score <= urgent_threshold_pct -> POSSIBLE ANOMALY
    # combined_score > urgent_threshold_pct            -> URGENT REVIEW
    # Defaults loosely mirror the pitch deck's health-score bands
    # (health = 100 - combined_score): 80+/60-80/40-60/<40.
    "anomaly_threshold_pct": 20.0,
    "urgent_threshold_pct": 60.0,
    "min_quality_samples": 5,        # minimum samples required in a trial to be considered valid

    # --- Data ---
    "storage_dir": DATA_DIR,
}


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_settings() -> dict:
    """Load settings from disk, falling back to defaults for any missing keys."""
    ensure_data_dir()
    settings = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r") as f:
                saved = json.load(f)
            settings.update(saved)
        except (json.JSONDecodeError, OSError):
            # Corrupted settings file -> fall back to defaults rather than crashing
            pass
    return settings


def save_settings(settings: dict) -> None:
    ensure_data_dir()
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)
