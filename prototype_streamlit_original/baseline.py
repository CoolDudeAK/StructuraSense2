"""
baseline.py
-----------
Baseline calibration engine.

"Baseline" represents the normal (intact-specimen) vibration response
under the defined excitation procedure. It is calculated from a series
of real trials performed by the user on the INTACT specimen — never
hard-coded.

Storage format (data/baseline.json):
{
  "sensor1_mean": 0.0, "sensor1_std": 0.0,
  "sensor2_mean": 0.0, "sensor2_std": 0.0,
  "sensor3_mean": 0.0, "sensor3_std": 0.0,
  "num_trials": 0,
  "created_at": "...",
  "specimen_id": "..."
}
"""

import json
import os
from datetime import datetime

from signal_processing import calculate_mean, calculate_standard_deviation

BASELINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "baseline.json")


def calculate_baseline(trials: list, specimen_id: str = "default") -> dict:
    """
    trials: list of dicts, each with keys sensor1, sensor2, sensor3
            (one representative peak-to-peak value per trial, per sensor)
    Returns the baseline statistics dict (not yet saved to disk).
    """
    s1_vals = [t["sensor1"] for t in trials]
    s2_vals = [t["sensor2"] for t in trials]
    s3_vals = [t["sensor3"] for t in trials]

    return {
        "sensor1_mean": calculate_mean(s1_vals),
        "sensor1_std": calculate_standard_deviation(s1_vals),
        "sensor2_mean": calculate_mean(s2_vals),
        "sensor2_std": calculate_standard_deviation(s2_vals),
        "sensor3_mean": calculate_mean(s3_vals),
        "sensor3_std": calculate_standard_deviation(s3_vals),
        "num_trials": len(trials),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "specimen_id": specimen_id,
    }


def save_baseline(baseline: dict, path: str = BASELINE_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(baseline, f, indent=2)


def load_baseline(path: str = BASELINE_PATH):
    """Returns the baseline dict, or None if no baseline has been saved yet."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def baseline_is_valid(baseline) -> bool:
    if not baseline:
        return False
    required = ["sensor1_mean", "sensor2_mean", "sensor3_mean"]
    return all(k in baseline for k in required) and baseline.get("num_trials", 0) > 0
