"""
anomaly_detection.py
---------------------
Transparent, rule-based anomaly detection for the StructuraSense prototype.

IMPORTANT / HONESTY NOTE:
This is a proof-of-concept algorithm, not a validated engineering method.
It compares the current piezo peak-to-peak response of each sensor against
an experimentally-collected baseline (mean of many "intact" trials) and
flags a large relative deviation as a "POSSIBLE ANOMALY". It does NOT
detect cracks directly, does not estimate crack width/depth, and is not a
substitute for professional structural inspection.

--------------------------------------------------------------------------
HOW THE SCORE IS CALCULATED (documented per project requirement #36):

For each sensor i:
    deviation_i (%) = |current_i - baseline_mean_i| / baseline_mean_i * 100

combined_anomaly_score = average of the three per-sensor deviations
    (this is the number shown as "Anomaly Score")

Prototype Health Score = max(0, 100 - combined_anomaly_score)
    (100 = current response identical to baseline, 0 = response is at
    least 100% different from baseline on average)

classify_status() uses TWO configurable thresholds (Settings page) to
produce a 3-tier status, loosely mirroring the health-score bands shown
in the project pitch deck (Optimal / Routine check-Inspection needed /
Urgent repair):

    combined_score <= anomaly_threshold_pct                -> "NORMAL"
    anomaly_threshold_pct < score <= urgent_threshold_pct   -> "POSSIBLE ANOMALY"
    combined_score > urgent_threshold_pct                   -> "URGENT REVIEW"

Both thresholds should be determined experimentally by comparing intact
vs. damaged trials on the physical specimen — they are NOT pre-validated
engineering limits.
--------------------------------------------------------------------------
"""

from signal_processing import calculate_deviation

STATUS_NORMAL = "NORMAL"
STATUS_ANOMALY = "POSSIBLE ANOMALY"
STATUS_URGENT = "URGENT REVIEW"


def calculate_anomaly_score(current: dict, baseline: dict) -> dict:
    """
    current:  {"sensor1": val, "sensor2": val, "sensor3": val}
    baseline: {"sensor1_mean": val, "sensor2_mean": val, "sensor3_mean": val, ...}

    Returns a dict with per-sensor deviation %, the combined anomaly
    score, the largest-deviation sensor, and the prototype health score.
    """
    dev1 = calculate_deviation(current.get("sensor1", 0), baseline.get("sensor1_mean"))
    dev2 = calculate_deviation(current.get("sensor2", 0), baseline.get("sensor2_mean"))
    dev3 = calculate_deviation(current.get("sensor3", 0), baseline.get("sensor3_mean"))

    deviations = {"sensor1": dev1, "sensor2": dev2, "sensor3": dev3}
    combined_score = sum(deviations.values()) / 3.0
    health_score = max(0.0, 100.0 - combined_score)
    largest_sensor = max(deviations, key=deviations.get)

    return {
        "deviations": deviations,
        "combined_score": combined_score,
        "health_score": health_score,
        "largest_deviation_sensor": largest_sensor,
    }


def classify_status(combined_score: float, threshold_pct: float, urgent_threshold_pct: float = None) -> str:
    """
    Classify overall structural status given the combined anomaly score.

    threshold_pct: NORMAL vs POSSIBLE ANOMALY boundary.
    urgent_threshold_pct: POSSIBLE ANOMALY vs URGENT REVIEW boundary.
                           If omitted, only the 2-tier NORMAL/POSSIBLE
                           ANOMALY classification is used.
    """
    if combined_score <= threshold_pct:
        return STATUS_NORMAL
    if urgent_threshold_pct is not None and combined_score > urgent_threshold_pct:
        return STATUS_URGENT
    return STATUS_ANOMALY
