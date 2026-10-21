# Hardware guide
## 1 · Your Arduino UNO + 3 piezo (Impact Lab)
Sketch: `firmware/arduino_p2p/StructuraSense_TestFirmware.ino` (unchanged from your prototype). Prints `s1,s2,s3` peak-to-peak every loop at 115200 baud.
- Set `USE_SIMULATED_DATA = false` for real sensors. Use a protection circuit (resistor + clamp diodes) — never wire a bare piezo to an analog pin.
- Connect from the browser (Impact Lab → Connect Arduino; Chrome/Edge) **or** run `python tools/serial_bridge.py --structure STR-001 --port COM3 --email engineer@vitaforge.demo --password Sense@2026`.
- Only one program can hold the serial port: close the Arduino Serial Monitor first.
- Packets outside 0–5000 or malformed lines are rejected and counted, never stored.

## 2 · ESP32 over Wi-Fi
1. Connect Data → Devices → **Add device** (type, unit, zone). Copy the key (shown once).
2. Run the server with `python run.py --host 0.0.0.0`; find your computer's IP (`ipconfig` / `ifconfig`).
3. Edit and flash `firmware/esp32_http/esp32_http.ino`. Replies: 200 ok · 401 wrong key · 404 unknown id.
Allow Python through your firewall when asked. Use only on a network you trust.

## 3 · Raw vibration from an Arduino (optional)
`firmware/arduino_piezo/arduino_piezo_waveform.ino` sends `W|device|rate|samples…` lines; forward with the bridge script. The server computes FFT, dominant frequency, damping and compares with the baseline.

## 4 · CSV
Long (`timestamp,device_id,value`), wide (`time,<device ids…>`) or raw waveform (single column + sample rate). Examples in `data/`.

## Provenance rule
Data from sensors = LIVE (teal). Files = FILE. Simulator = SIMULATED (violet). A structure's *Health uses* switch can show real-only, simulated-only or all.


## 5 · The seven device families
| Device | Typical hardware | Send as `kind` | Unit |
|---|---|---|---|
| Strain gauge | foil gauge + HX711 / ADS1115 | `strain` | microstrain |
| WIM sensor | piezo / load-cell axle sensor | `wim` | kN |
| Accelerometer | ADXL345 / MPU6050 / piezo | `accelerometer`, `piezo` | g or Hz |
| LVDT | LVDT + signal conditioner | `lvdt` | mm |
| Temperature | DS18B20 / thermocouple | `temperature` | C |
| Moisture probe | capacitive or resistive probe | `moisture` | % |
| RF coil (experimental) | LC coil + frequency counter | `rf_coil` | kHz (resonant frequency) |

Create the device under *Connect Data*, copy its key, and send readings to `/api/ingest/readings` like any other device. A channel becomes ACTIVE as soon as one of its devices reports; until then it is INACTIVE and does not affect the score. The RF coil is an **experimental** concept with no Indian Standard: the app only compares its resonance with a baseline.
