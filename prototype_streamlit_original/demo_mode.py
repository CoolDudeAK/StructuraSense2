"""
demo_mode.py
------------
Simulated sensor data generator used when the Arduino is disconnected —
essential for hackathon demos that must keep working even if the USB
connection drops or judges want to see the software without hardware.

All data produced here is clearly and permanently labelled as simulated
(data_source = "DEMO/SIMULATION DATA") everywhere it is stored or shown,
per the project's honesty requirements. It is NEVER mixed silently with
real hardware readings.

Implements the SAME interface as SerialReader (is_connected, get_latest,
get_buffer, get_raw_log) so the rest of the app can treat a live Arduino
and the demo generator interchangeably.
"""

import random
import threading
import time
from collections import deque
from datetime import datetime

BUFFER_MAXLEN = 1000
RAW_LOG_MAXLEN = 300

DEFAULT_BASELINE = {
    "sensor1_mean": 180.0, "sensor1_std": 6.0,
    "sensor2_mean": 165.0, "sensor2_std": 6.0,
    "sensor3_mean": 174.0, "sensor3_std": 6.0,
}


class DemoGenerator:
    """Generates simulated piezo readings in a background thread."""

    def __init__(self):
        self._thread = None
        self._stop_flag = threading.Event()
        self._lock = threading.Lock()
        self._buffer = deque(maxlen=BUFFER_MAXLEN)
        self._raw_log = deque(maxlen=RAW_LOG_MAXLEN)
        self.scenario = "normal"   # "normal" or "anomaly"
        self._active = False

    @property
    def is_connected(self) -> bool:
        return self._active

    def set_scenario(self, scenario: str):
        assert scenario in ("normal", "anomaly")
        self.scenario = scenario

    def start(self, baseline: dict = None, interval: float = 0.2):
        self.stop()
        self._baseline = baseline or DEFAULT_BASELINE
        self._interval = interval
        self._stop_flag.clear()
        self._active = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_flag.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
        self._active = False

    def _loop(self):
        while not self._stop_flag.is_set():
            b = self._baseline
            if self.scenario == "normal":
                s1 = random.gauss(b["sensor1_mean"], b.get("sensor1_std", 6.0))
                s2 = random.gauss(b["sensor2_mean"], b.get("sensor2_std", 6.0))
                s3 = random.gauss(b["sensor3_mean"], b.get("sensor3_std", 6.0))
            else:
                # Simulate a damaged specimen: one or more sensors shift
                # significantly relative to baseline (larger deviation).
                s1 = random.gauss(b["sensor1_mean"] * 1.05, b.get("sensor1_std", 6.0))
                s2 = random.gauss(b["sensor2_mean"] * 0.70, b.get("sensor2_std", 6.0) * 2)
                s3 = random.gauss(b["sensor3_mean"] * 1.10, b.get("sensor3_std", 6.0))

            s1, s2, s3 = max(0.0, s1), max(0.0, s2), max(0.0, s3)
            reading = {"timestamp": datetime.now(), "s1": s1, "s2": s2, "s3": s3}
            line = f"{s1:.1f},{s2:.1f},{s3:.1f}  [SIMULATED - {self.scenario.upper()}]"
            with self._lock:
                self._buffer.append(reading)
                self._raw_log.append(line)
            time.sleep(self._interval)

    def get_latest(self):
        with self._lock:
            if not self._buffer:
                return None
            return dict(self._buffer[-1])

    def get_buffer(self):
        with self._lock:
            return list(self._buffer)

    def get_raw_log(self):
        with self._lock:
            return list(self._raw_log)

    def clear_raw_log(self):
        with self._lock:
            self._raw_log.clear()

    def clear_buffer(self):
        with self._lock:
            self._buffer.clear()

    def get_last_error(self):
        return None
