"""Forward an Arduino's USB serial lines to StructuraSense (no browser needed).

  pip install pyserial requests
  python tools/serial_bridge.py --structure STR-001 --email engineer@vitaforge.demo --password Sense@2026
  python tools/serial_bridge.py --port COM3 --structure STR-002 --device-key ssk_xxx      (single sensor, device key)

Lines understood by the server:
  184,126,171                 or  S1:184,S2:126,S3:171     (your 3-piezo rig)
  S|<device_id>|<value>                                    (one sensor reading)
  W|<device_id>|<sample_rate>|v1,v2,v3,...                 (one raw vibration capture, 64+ samples)
"""
import argparse, sys, time

try:
    import requests, serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("Missing packages. Run:  pip install pyserial requests")

ap = argparse.ArgumentParser()
ap.add_argument("--server", default="http://127.0.0.1:5000")
ap.add_argument("--port", help="e.g. COM3 or /dev/ttyUSB0 (omit to list ports)")
ap.add_argument("--baud", type=int, default=115200)
ap.add_argument("--structure", help="structure id, e.g. STR-001")
ap.add_argument("--email"); ap.add_argument("--password")
ap.add_argument("--device-key", help="device key (X-Device-Key) instead of a login")
a = ap.parse_args()

ports = list(list_ports.comports())
if not a.port:
    print("Available serial ports:")
    for p in ports: print(f"  {p.device}  {p.description}")
    sys.exit("\nRe-run with --port <name>.")

headers = {}
if a.device_key:
    headers["X-Device-Key"] = a.device_key
elif a.email and a.password:
    r = requests.post(a.server + "/api/auth/login", json={"email": a.email, "password": a.password}, timeout=10)
    if r.status_code != 200: sys.exit("Login failed: " + r.text)
    headers["Authorization"] = "Bearer " + r.json()["token"]
else:
    sys.exit("Give --email and --password, or --device-key.")

ser = serial.Serial(a.port, a.baud, timeout=1)
print(f"Reading {a.port} at {a.baud} baud -> {a.server}   (Ctrl+C to stop)")
buf, last, sent, bad = [], time.time(), 0, 0
try:
    while True:
        line = ser.readline().decode("utf-8", "ignore").strip()
        if line: buf.append(line)
        if buf and (time.time() - last > 0.25 or len(buf) >= 200):
            try:
                r = requests.post(a.server + "/api/ingest/serial-lines", json={"structure_id": a.structure, "lines": buf}, headers=headers, timeout=10)
                j = r.json()
                sent += j.get("accepted", 0); bad += j.get("rejected", 0)
                if r.status_code != 200: print("Server said:", j)
            except requests.RequestException as e:
                print("Cannot reach server:", e)
            buf, last = [], time.time()
            print(f"\raccepted {sent}  rejected {bad}", end="", flush=True)
except KeyboardInterrupt:
    print("\nStopped.")
