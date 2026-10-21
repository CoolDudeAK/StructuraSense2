"""
signal_processing.py
---------------------
Basic, transparent signal-processing functions used to summarize a batch
of piezo sensor readings collected during a trial.

Every function here is deliberately simple and well-documented so a
non-specialist can verify exactly what is being computed. No hidden
"black box" processing is used in this prototype.
"""

import math


def calculate_peak_to_peak(values):
    """Peak-to-peak = max - min of a list of readings."""
    if not values:
        return 0.0
    return float(max(values) - min(values))


def calculate_mean(values):
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def calculate_standard_deviation(values):
    """Population standard deviation."""
    if not values or len(values) < 2:
        return 0.0
    mean = calculate_mean(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return float(math.sqrt(variance))


def calculate_energy_proxy(values):
    """
    A simple proxy for vibrational "energy": mean of squared readings.
    This is NOT a calibrated physical energy unit — it is a relative
    indicator useful for comparing trials against each other.
    """
    if not values:
        return 0.0
    return float(sum(v ** 2 for v in values) / len(values))


def calculate_deviation(current, baseline):
    """
    Percentage deviation of a current value from its baseline:
        deviation% = |current - baseline| / baseline * 100

    Returns 0 if baseline is 0 or missing (avoids division by zero).
    """
    if baseline is None or baseline == 0:
        return 0.0
    return float(abs(current - baseline) / baseline * 100.0)


def summarize_trial(sensor1_values, sensor2_values, sensor3_values):
    """
    Convenience helper: given lists of raw samples collected for each
    sensor during a trial, return the standard summary statistics used
    throughout the app.
    """
    summary = {}
    for name, values in (("sensor1", sensor1_values), ("sensor2", sensor2_values), ("sensor3", sensor3_values)):
        summary[name] = {
            "peak_to_peak": calculate_peak_to_peak(values),
            "mean": calculate_mean(values),
            "std": calculate_standard_deviation(values),
            "energy": calculate_energy_proxy(values),
            "max": max(values) if values else 0.0,
            "min": min(values) if values else 0.0,
        }
    return summary
