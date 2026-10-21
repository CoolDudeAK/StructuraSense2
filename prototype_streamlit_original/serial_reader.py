"""
serial_reader.py
----------------
Handles ALL communication with the Arduino UNO over USB serial.

Responsibilities (and only these — no UI code lives here):
  * detecting available COM ports
  * opening / closing the serial connection
  * reading incoming lines in a background thread (so the UI never freezes)
  * parsing raw sensor packets into numeric values
  * validating incoming data and reporting errors instead of crashing

Expected packet formats (either is accepted):
  Format A:  "S1:184,S2:126,S3:171"
  Format B:  "184,126,171"

The parser is intentionally isolated in `parse_line()` so the Arduino
firmware's format can be changed later without touching anything else.
"""

import re
import threading
import time
from collections import deque
from datetime import datetime

try:
    import serial
    import serial.tools.list_ports
    PYSERIAL_AVAILABLE = True
except ImportError:  # pyserial not installed yet
    PYSERIAL_AVAILABLE = False

# Reasonable sanity bounds for a piezo peak-to-peak reading coming from an
# Arduino analogRead() style pipeline (0-1023 raw, but allow headroom for
# amplified / pre-scaled firmware).
MIN_VALID_VALUE = 0
MAX_VALID_VALUE = 5000

BUFFER_MAXLEN = 1000       # rolling window of parsed readings kept in memory
RAW_LOG_MAXLEN = 300       # rolling window of raw serial lines kept for the Serial Monitor


def list_ports():
    """Return a list of available COM/serial port device names."""
    if not PYSERIAL_AVAILABLE:
        return []
    return [p.device for p in serial.tools.list_ports.comports()]


class SerialReadError(Exception):
    """Raised when a line cannot be parsed into 3 valid sensor values."""
    pass


def parse_line(line: str):
    """
    Parse one line of raw serial text into (s1, s2, s3) floats.
    Accepts "S1:184,S2:126,S3:171" or "184,126,171".
    Raises SerialReadError on anything invalid (empty, non-numeric,
    wrong count, out-of-range, corrupted).
    """
    if line is None:
        raise SerialReadError("Empty packet received.")

    line = line.strip()
    if not line:
        raise SerialReadError("Empty packet received.")

    # Format A: labelled key:value pairs, order-independent
    if "S1" in line.upper() or ":" in line:
        matches = re.findall(r"[Ss]\s*[123]\s*:\s*(-?\d+\.?\d*)", line)
        if len(matches) == 3:
            values = [float(m) for m in matches]
        else:
            raise SerialReadError(f"Could not parse labelled packet: '{line}'")
    else:
        # Format B: plain comma-separated numbers
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            raise SerialReadError(f"Expected 3 comma-separated values, got {len(parts)}: '{line}'")
        try:
            values = [float(p) for p in parts]
        except ValueError:
            raise SerialReadError(f"Non-numeric value in packet: '{line}'")

    for v in values:
        if v != v:  # NaN check
            raise SerialReadError("Invalid (NaN) value in packet.")
        if v < MIN_VALID_VALUE or v > MAX_VALID_VALUE:
            raise SerialReadError(f"Value {v} outside plausible sensor range.")

    return tuple(values)


class SerialReader:
    """
    Manages a background thread that continuously reads and parses lines
    from an Arduino connected over USB serial.

    This class is UI-framework-agnostic: Streamlit pages simply call
    connect() / disconnect() / get_latest() / get_buffer() / get_raw_log().
    """

    def __init__(self):
        self._serial = None
        self._thread = None
        self._stop_flag = threading.Event()
        self._lock = threading.Lock()

        self._buffer = deque(maxlen=BUFFER_MAXLEN)     # list of dicts: {timestamp, s1, s2, s3}
        self._raw_log = deque(maxlen=RAW_LOG_MAXLEN)    # list of raw strings (with markers for errors)
        self._last_error = None
        self.port = None
        self.baud_rate = None

    # ---------- connection management ----------

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self, port: str, baud_rate: int = 115200) -> (bool, str):
        if not PYSERIAL_AVAILABLE:
            return False, "pyserial is not installed. Run: pip install pyserial"

        self.disconnect()  # ensure clean state first

        try:
            self._serial = serial.Serial(port, baud_rate, timeout=1)
            time.sleep(2)  # allow Arduino to reset after opening the port
        except Exception as e:
            self._serial = None
            return False, f"Could not open {port}: {e}"

        self.port = port
        self.baud_rate = baud_rate
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()
        return True, f"Connected to {port} at {baud_rate} baud."

    def disconnect(self):
        self._stop_flag.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self.port = None

    # ---------- background reading ----------

    def _reader_loop(self):
        while not self._stop_flag.is_set():
            if self._serial is None or not self._serial.is_open:
                break
            try:
                raw = self._serial.readline()
                if not raw:
                    continue  # timeout with no data - normal, keep looping
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    s1, s2, s3 = parse_line(line)
                    reading = {
                        "timestamp": datetime.now(),
                        "s1": s1,
                        "s2": s2,
                        "s3": s3,
                    }
                    with self._lock:
                        self._buffer.append(reading)
                        self._raw_log.append(line)
                        self._last_error = None
                except SerialReadError as e:
                    with self._lock:
                        self._raw_log.append(f"[INVALID] {line}")
                        self._last_error = str(e)
            except Exception as e:
                with self._lock:
                    self._last_error = f"Serial read error: {e}"
                time.sleep(0.5)

    # ---------- data access (thread-safe) ----------

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
        with self._lock:
            return self._last_error
