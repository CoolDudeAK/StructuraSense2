"""
Baseline Calibration — establish the "normal" (intact specimen) response
that all future readings are compared against.
"""
import time

import streamlit as st

from baseline import calculate_baseline, load_baseline, save_baseline
from config import load_settings
from signal_processing import calculate_peak_to_peak
from state import get_app_state
from ui_helpers import inject_css, page_header

st.set_page_config(page_title="Calibration · StructuraSense", page_icon="📏", layout="wide")
inject_css()

app_state = get_app_state()
settings = load_settings()
source = app_state.get_active_source()

page_header(connected=source is not None, source_label=app_state.data_source_label())

st.title("Baseline Calibration")
st.info(
    "Baseline represents the normal response of the intact concrete specimen "
    "under the defined excitation procedure."
)

with st.expander("Calibration steps", expanded=False):
    st.markdown(
        "**Step 1** — Place sensors on the specimen.\n\n"
        "**Step 2** — Select **INTACT SPECIMEN** (this page assumes intact).\n\n"
        "**Step 3** — Perform repeated, consistent impacts.\n\n"
        f"**Step 4** — Record approximately {settings['num_baseline_trials']} trials.\n\n"
        "**Step 5** — Calculate baseline statistics and save."
    )

if source is None:
    st.warning("No active data source. Connect the Arduino (Device page) or start Demo Mode (Dashboard page) before calibrating.")
    st.stop()

target_trials = settings["num_baseline_trials"]
trials = app_state.calibration_trials
specimen_id = st.text_input("Specimen Identifier", value="specimen-1")
impact_window = st.number_input("Seconds to record per impact", min_value=1, max_value=15, value=3)

st.markdown(f"### Trials Completed: {len(trials)} / {target_trials}")
st.progress(min(1.0, len(trials) / target_trials))

c1, c2, c3 = st.columns(3)
with c1:
    if st.button("➕ Record One Trial", type="primary", width='stretch'):
        s1_vals, s2_vals, s3_vals = [], [], []
        progress = st.progress(0, text="Recording impact...")
        start = time.time()
        while time.time() - start < impact_window:
            latest = source.get_latest()
            if latest is not None:
                s1_vals.append(latest["s1"])
                s2_vals.append(latest["s2"])
                s3_vals.append(latest["s3"])
            elapsed = time.time() - start
            progress.progress(min(1.0, elapsed / impact_window), text=f"Recording... {elapsed:.1f}s")
            time.sleep(settings["sampling_interval_sec"])
        if len(s1_vals) < 2:
            st.error("Not enough samples captured — check the connection and try again.")
        else:
            trials.append({
                "sensor1": calculate_peak_to_peak(s1_vals),
                "sensor2": calculate_peak_to_peak(s2_vals),
                "sensor3": calculate_peak_to_peak(s3_vals),
            })
            st.rerun()

with c2:
    if st.button("↩ Undo Last Trial", width='stretch', disabled=(len(trials) == 0)):
        trials.pop()
        st.rerun()

with c3:
    if st.button("🗑 Clear All Trials", width='stretch', disabled=(len(trials) == 0)):
        trials.clear()
        st.rerun()

if trials:
    stats = calculate_baseline(trials, specimen_id)
    st.divider()
    st.subheader("BASELINE CALIBRATION")
    b1, b2, b3 = st.columns(3)
    for col, i in zip((b1, b2, b3), (1, 2, 3)):
        with col:
            st.markdown(f"**Sensor {i}**")
            st.metric("Mean", f"{stats[f'sensor{i}_mean']:.2f}")
            st.metric("Std Dev", f"{stats[f'sensor{i}_std']:.2f}")

    if len(trials) < target_trials:
        st.warning(f"More baseline trials required. ({len(trials)} / {target_trials})")

    if st.button("💾 SAVE BASELINE", type="primary", disabled=(len(trials) < 3)):
        save_baseline(stats)
        app_state.calibration_trials = []
        st.success("Baseline saved. Anomaly detection is now active on the Dashboard.")
        st.rerun()

st.divider()
existing = load_baseline()
if existing:
    st.subheader("Current Saved Baseline")
    st.json(existing)
else:
    st.caption("No baseline saved yet.")
