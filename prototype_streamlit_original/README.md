# StructuraSense — Live Prototype Software

**AI-Assisted Structural Health Monitoring System**
Team NexaStruc · MSME 6.0 Hackathon cum Start-up Contest

StructuraSense is the laptop-side software for a physical prototype consisting of an Arduino UNO
and 3 piezoelectric sensors mounted on a concrete specimen. It reads live sensor data over USB,
compares it against a baseline you calibrate experimentally, and reports whether the structural
response is **NORMAL**, a **POSSIBLE ANOMALY**, or needs **URGENT REVIEW**.

> ⚠️ **Prototype limitation:** This system identifies *changes in measured vibration response*.
> It does **not** detect exact crack width/depth, does not certify structural safety, and does
> **not** replace professional structural inspection.

---

## 1. Features

- Live Arduino USB-serial communication (background thread, non-blocking UI)
- Real-time sensor readings + live multi-trace chart (pause / resume / clear / window size)
- Guided trial recording (Intact vs Damaged specimen)
- Baseline calibration workflow (mean/std from real trials — never hard-coded)
- Transparent rule-based anomaly detection with a documented formula
- 3-tier status: NORMAL / POSSIBLE ANOMALY / URGENT REVIEW (configurable thresholds)
- SQLite-backed trial history with filters + CSV export
- Data Analysis page: Intact vs Damaged comparison, deviation stats, variability
- Demo Mode: clearly-labelled simulated data so the app works without hardware
- Full offline operation — no cloud, no accounts, no API keys

## 2. Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit (Python) |
| Serial communication | pyserial |
| Data processing | pandas, numpy |
| Storage | SQLite (trial history) + JSON (baseline) + CSV (export) |

## 3. Project Structure

```
StructuraSense/
├── app.py                      # entry point
├── config.py                   # settings persistence
├── serial_reader.py            # Arduino USB serial communication + parsing
├── signal_processing.py        # peak-to-peak, mean, std, energy proxy
├── anomaly_detection.py        # anomaly score + NORMAL/ANOMALY/URGENT classification
├── baseline.py                 # baseline calibration engine
├── data_storage.py             # SQLite trial history + CSV export
├── demo_mode.py                # simulated data generator (clearly labelled)
├── state.py                    # shared app-state singleton (keeps serial/demo alive across reruns)
├── ui_helpers.py                # shared CSS + card components
├── pages/
│   ├── 1_Dashboard.py
│   ├── 2_Device.py
│   ├── 3_Experiment.py
│   ├── 4_Baseline_Calibration.py
│   ├── 5_Analysis.py
│   ├── 6_History.py
│   ├── 7_Settings.py
│   └── 8_About.py
├── arduino_firmware/
│   └── StructuraSense_TestFirmware.ino
├── data/                        # created automatically: settings.json, baseline.json, structurasense.db
├── requirements.txt
└── README.md
```

## 4. Windows Installation (beginner-friendly, step by step)

### Step 1 — Install Python
Download Python 3.10+ from https://python.org/downloads and run the installer.
**Important:** check the box "Add Python to PATH" during installation.

### Step 2 — Get the project folder
Copy the entire `StructuraSense` folder onto your computer (e.g. `C:\StructuraSense`).

### Step 3 — Open a terminal in that folder
In File Explorer, open the `StructuraSense` folder, click the address bar, type `cmd`, press Enter.

### Step 4 — Install dependencies
```
pip install -r requirements.txt
```

### Step 5 — Connect the Arduino
Plug the Arduino UNO into a USB port on your computer.

### Step 6 — Find the COM port
Open Windows Device Manager → "Ports (COM & LPT)" → note the COM number (e.g. `COM3`).
(You can also just click "Refresh Ports" inside the app's Device page.)

### Step 7 — Run the app
```
streamlit run app.py
```

### Step 8 — Open the app
Your browser should open automatically to `http://localhost:8501`. If not, open that address manually.

## 5. Arduino Setup

1. Open `arduino_firmware/StructuraSense_TestFirmware.ino` in the Arduino IDE.
2. Upload it to your Arduino UNO.
3. By default it sends **simulated** random values in the correct format (`184,126,171`) so you
   can test the software immediately — no sensors required yet.
4. Once your 3 piezo sensors are wired to A0, A1, A2, open the `.ino` file and change:
   ```cpp
   const bool USE_SIMULATED_DATA = true;   // change to false
   ```
   Re-upload. No other code changes are needed.

**Hardware safety note:** this firmware assumes a basic piezo-to-analog-input protection circuit.
Do not wire a bare piezo element directly into an analog pin without a current-limiting /
voltage-clamping circuit — verify your specific circuit design separately.

## 6. Using the App

1. **Device** page → Refresh Ports → select your Arduino's COM port → Connect.
2. **Baseline Calibration** page → record ~20–30 trials on the **intact** specimen → Save Baseline.
3. **Experiment** page → select condition (Intact/Damaged) → Start Trial → perform a controlled
   impact → review the NORMAL / POSSIBLE ANOMALY / URGENT REVIEW result.
4. **History** page → filter, review, and Export CSV (opens directly in Excel).
5. **Analysis** page → compare Intact vs Damaged statistics across all recorded trials.
6. **Settings** page → tune anomaly thresholds, trial duration, sampling interval, etc.

## 7. Demo Mode (no hardware required)

On the **Dashboard** page, open "🎮 Demo Mode" and click **Simulate NORMAL** or **Simulate
ANOMALY**. This generates clearly labelled simulated data (`⚠ DEMO MODE — SIMULATED DATA`) so you
can demonstrate the full workflow — dashboard, trials, baseline comparison — even without the
Arduino connected. Demo data is never mixed with real hardware readings without being labelled.

## 8. How the Anomaly Score Works (fully transparent)

For each sensor:
```
deviation_i (%) = |current_i - baseline_mean_i| / baseline_mean_i × 100
```
```
combined_anomaly_score = average of the 3 per-sensor deviations
Prototype Health Score = max(0, 100 - combined_anomaly_score)
```
Classification (both thresholds are configurable in Settings):
```
combined_score ≤ anomaly_threshold_pct                  → NORMAL
anomaly_threshold_pct < score ≤ urgent_threshold_pct     → POSSIBLE ANOMALY
combined_score > urgent_threshold_pct                    → URGENT REVIEW
```
These thresholds should be determined experimentally by comparing your own intact vs. damaged
trials — they are not pre-validated engineering limits.

## 9. Real vs Simulated vs Future

| Component | Status |
|---|---|
| Arduino USB serial communication | ✅ Real |
| Live sensor readings + chart | ✅ Real (from Arduino, or simulated in Demo Mode) |
| Baseline calibration | ✅ Real (computed from your actual trials) |
| Rule-based anomaly detection | ✅ Real, fully transparent formula |
| SQLite trial history + CSV export | ✅ Real |
| Demo Mode | ✅ Real feature, clearly-labelled simulated data |
| Machine learning classification (Random Forest, etc.) | 🔶 Future — architecture allows it once labelled data is collected |
| Computer vision crack detection (CNN/YOLO) | 🔶 Future — requires camera hardware + trained model |
| Multi-sensor fusion (strain, load, temperature, accelerometer) | 🔶 Future — requires additional sensor hardware |
| Cloud dashboard / multi-site monitoring | 🔶 Future — requires backend + hosting infrastructure |

## 10. Troubleshooting

**"No COM ports detected"**
→ Check the USB cable, try a different USB port, install Arduino USB drivers (CH340/FTDI if
using a clone board), then click Refresh Ports.

**"Could not open COMx"**
→ Close the Arduino IDE's Serial Monitor (only one program can use the port at a time).

**"Waiting for sensor data..."**
→ Confirm the Arduino is sending data (check Device page → Serial Monitor). Confirm baud rate
matches (`115200` by default) on both firmware and Settings.

**"Invalid sensor packet received"**
→ The Arduino is sending text in an unexpected format. Confirm it matches `184,126,171` or
`S1:184,S2:126,S3:171`. The app skips invalid lines instead of crashing.

**"Baseline not available"**
→ Complete Baseline Calibration and click Save Baseline before running anomaly detection.

**App won't start / `ModuleNotFoundError`**
→ Run `pip install -r requirements.txt` again inside the project folder.

**Port already in use (`streamlit run` fails)**
→ Run `streamlit run app.py --server.port 8502` instead.

## 11. Team

**NexaStruc** — MSME 6.0 Hackathon cum Start-up Contest
Dinkee Kumari (Team Lead), Adarsh Kumar, Vivek Kumar, Rahul Kumar, Manish Kumar Gupta, Divya Kumari
