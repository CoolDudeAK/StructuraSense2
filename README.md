# StructuraSense — structural health monitoring prototype (Team VitaForge)

A working full-stack prototype: **sensors / simulator → API → database → health index → alerts → dashboard**.
It includes **Impact Lab**, which runs your own Arduino UNO + 3 piezo specimen workflow (ported from your Streamlit prototype, which is kept untouched in `prototype_streamlit_original/`).

> **Decision-support prototype, not a safety certificate.** Scores and alerts help an engineer decide where to look; they do not replace inspection.

## What is real and what is simulated
| Status | What |
|---|---|
| **REAL** | Web app, REST API, SQLite database, login + roles, health-index maths, alerts, maintenance approval flow, FFT/vibration analysis, rainflow fatigue, crack detection (classical image processing), CSV import, Arduino USB input (browser Web Serial + bridge script), ESP32/HTTP ingest with device keys, Supabase mirror code |
| **SIMULATED** | Element Test Lab simulated sensors, RF-coil readings (experimental), demo bridges/flyover sensor streams, the demo tap simulator in Impact Lab, anomaly/health-forest/load models are *trained on simulated data*. Everything simulated is tagged violet **SIMULATED** in the app. |
| **NEEDS YOUR HARDWARE / ACCOUNT** | Real Arduino readings, ESP32, a Supabase project, weather lookup (needs internet) |
| **FUTURE** | YOLO/CNN crack model (slot ready), LSTM fatigue model, Firebase adapter, drones, real RF-coil hardware |

The in-app page **"What is real?"** lists all of this. Not yet tested: your physical Arduino, a live Supabase project, real concrete photos.

## Run it (beginner steps)
1. **Install Python 3.10 or newer** from python.org. On Windows tick **"Add Python to PATH"** in the installer.
2. **Open a terminal in this folder.** Windows: open the folder in File Explorer, click the address bar, type `cmd`, press Enter. Mac: right-click the folder → *New Terminal at Folder*.
3. Install the parts (once, needs internet):
   ```
   pip install -r requirements.txt
   ```
   (If `pip` is not found, try `python -m pip install -r requirements.txt` or `python3 ...`.)
4. Start the app:
   ```
   python run.py
   ```
   The **first start takes about 10–20 seconds** (it builds the demo database and trains the small models). Wait for *"StructuraSense is running"*.
5. Open **Google Chrome or Microsoft Edge** and go to **http://127.0.0.1:5000**
6. Click **Engineer** on the sign-in page. Demo logins (password `Sense@2026`): `engineer@`, `admin@`, `viewer@` + `vitaforge.demo`.

Stop with `Ctrl+C`. Start fresh with `python run.py --reset`.

**If something goes wrong:** *"Address already in use"* → run `python run.py --port 5001` and open that port. *"No module named …"* → repeat step 3. Blank page → press Ctrl+F5.

## Try your Arduino rig (Impact Lab)
1. Upload `firmware/arduino_p2p/StructuraSense_TestFirmware.ino` with the Arduino IDE. **It starts in simulated mode** (`USE_SIMULATED_DATA = true`); set it to `false` once piezos are wired (with the protection circuit).
2. Close the Arduino IDE Serial Monitor. In the app: **Impact Lab → Connect Arduino → Connect**, pick the port.
3. **Baseline tab:** record 20 trials of the intact specimen → *Save as baseline*. **Live tab:** pick Intact/Damaged → *Start trial*.
No Arduino yet? Press **Start demo taps** on the Live tab (labelled SIMULATED).

Changes versus the Streamlit prototype (all documented in-app): live status compares a rolling window the length of a trial (the original compared one reading to a trial-sized baseline); the demo "anomaly" scenario was strengthened (it used to score ~15 %, below its own 20 % threshold) and a "severe" scenario added; data is stored in a database; trials also feed the structure health index and alerts. The team name in your zip said NexaStruc, the deck says VitaForge — VitaForge is used.

## Other data sources
- **ESP32 / Wi-Fi boards:** *Connect Data → Devices → Add device* (copy the key) → flash `firmware/esp32_http/esp32_http.ino`. Start the server with `python run.py --host 0.0.0.0`. See `docs/HARDWARE.md`.
- **CSV files:** *Connect Data → CSV import* (examples in `data/`).
- **Other Arduino sensors:** `python tools/serial_bridge.py` (see `docs/HARDWARE.md`).

## Cloud (Supabase)
Works fully offline by default. To mirror to Supabase: create a project → SQL Editor → run `database/supabase_schema.sql` → in the app, *Cloud & Settings* → paste Project URL and **service_role** key → Test → Upload. The key stays on the server and is never sent to the browser. Firebase would be a second adapter in `backend/services/cloud_sync.py` (not built).

## How it is built
- **Backend:** Python Flask, SQLite (WAL), NumPy/SciPy (signals), OpenCV + scikit-image (cracks), scikit-learn (models), PyJWT (login). Why not React/Node? The build environment could not download npm packages, so the front end is plain JavaScript modules with **no build step** — fewer installs for you.
- **Front end:** `frontend/` (served by Flask at `/`). Live updates by Server-Sent Events.
- **Database:** `database/schema.sql` (created automatically). **API:** `docs/API.md`.
- **Tests:** `python -m unittest discover -s tests -v` (54 tests, use a temporary database) and `python tests/e2e_walkthrough.py http://127.0.0.1:5000` (needs Playwright; screenshots to `tests/shots/`).

## Health index: seven device families, eight independent channels
Each device family is its own **channel** and scores itself 0-100. The overall Structural Health Score (SHS) is `sum(weight x score) / sum(weight)` over the **active** channels only, so even a single channel can produce a score. Inactive channels (no device, offline, filtered out) and channels an engineer switched off are shown as INACTIVE / DISABLED and are left out, not counted as zero. See the **Sensor channels** tab on any structure.

| Device | Parameter | Purpose | Channel | Weight |
|---|---|---|---|---|
| Strain gauges | Strain | Measure deformation | strain_fatigue | 12 % |
| WIM sensors | Load | Traffic load monitoring | load | 7 % |
| Accelerometers / piezo | Vibration | Detect stiffness change | vibration | 25 % |
| LVDT sensors | Deflection | Beam bending measurement | deflection | 12 % |
| Temperature sensors | Temperature | Thermal stress monitoring | thermal | 5 % |
| Moisture probes | Moisture | Detect water infiltration | environment | 8 % |
| RF coils (**experimental**, no IS code) | Internal discontinuity | Detect internal defects | internal | 6 % |
| Cameras (extra, from the original design) | Cracks | Measure crack width | cracks | 25 % |

Bands 80/60/40 and all weights are the team's proposals, not engineering standards.

## Element Test Lab (cubes, beams, slabs, columns)
Page **Element Tests (IS codes)**. Choose an element and a procedure (cube compression, beam flexure, beam/slab 24-hour load test, column axial test), then either run **simulated sensors** or type in **real readings**. Every sensor type (load, deflection, strain, vibration, temperature, moisture, RF coil, ultrasonic pulse velocity, crack imaging) gets its own result card with PASS / REVIEW / FAIL / INFO / INACTIVE, the limit used and its IS clause. Also: cube group compliance (4 results), CSV export, and real crack-width measurement from a photo. **Important:** the IS limits are the team's reading of IS 456 / IS 516 / IS 13311 from secondary sources and every one is flagged "verify"; check them against the purchased BIS text. Simulated tests are not certification. Details in `docs/IS_CODES.md`.

## Putting it online
See `docs/DEPLOY.md` (GitHub for the code, Vercel for the pages, Render for the Python back end).

## Known limitations
Prototype security (no HTTPS, simple login throttle); single-computer server; crack detector tuned on synthetic images only; ML models trained on simulated data; weather needs internet; Web Serial works only in Chrome/Edge desktop.
