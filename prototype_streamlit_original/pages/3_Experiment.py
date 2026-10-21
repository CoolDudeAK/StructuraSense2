"""
Experiment — guided workflow to run a controlled-impact trial and record
the resulting sensor response, condition, and anomaly classification.
"""
import time

import streamlit as st

from anomaly_detection import calculate_anomaly_score, classify_status
from baseline import baseline_is_valid, load_baseline
from config import load_settings
from data_storage import insert_trial
from signal_processing import summarize_trial
from state import get_app_state
from ui_helpers import disclaimer, inject_css, page_header, status_style

st.set_page_config(page_title="Experiment · StructuraSense", page_icon="🧪", layout="wide")
inject_css()

app_state = get_app_state()
settings = load_settings()
baseline = load_baseline()
source = app_state.get_active_source()

page_header(connected=source is not None, source_label=app_state.data_source_label())

st.title("Experiment")
st.caption("Run a controlled-impact trial and record the structural response.")

with st.expander("How the experiment works", expanded=False):
    st.markdown(
        "**STEP 1** — Prepare the concrete specimen.\n\n"
        "**STEP 2** — Verify sensor positions (S1, S2, S3 firmly attached).\n\n"
        "**STEP 3** — Select the specimen condition below.\n\n"
        "**STEP 4** — Perform a controlled impact (consistent tap location and force).\n\n"
        "**STEP 5** — Click **START TRIAL** — StructuraSense records the response.\n\n"
        "**STEP 6** — The response is automatically compared with baseline.\n\n"
        "**STEP 7** — Review the anomaly result below."
    )
    st.code(
        "             IMPACT\n"
        "                ↓\n\n"
        "       ┌─────────────────┐\n"
        "       │                 │\n"
        "       │    S1           │\n"
        "       │          S2     │\n"
        "       │    S3           │\n"
        "       │                 │\n"
        "       └─────────────────┘",
        language="text",
    )

if source is None:
    st.warning("No active data source. Connect the Arduino (Device page) or start Demo Mode (Dashboard page) before running a trial.")
    st.stop()

col1, col2 = st.columns([1, 1])
with col1:
    condition = st.radio("Specimen Condition", ["Intact", "Damaged"], horizontal=True)
with col2:
    duration = st.number_input("Trial Duration (seconds)", min_value=1, max_value=60,
                                value=int(settings["trial_duration_sec"]))

if st.button("▶ START TRIAL", type="primary"):
    s1_vals, s2_vals, s3_vals = [], [], []
    progress = st.progress(0, text="Recording trial...")
    start = time.time()
    interval = settings["sampling_interval_sec"]
    while time.time() - start < duration:
        latest = source.get_latest()
        if latest is not None:
            s1_vals.append(latest["s1"])
            s2_vals.append(latest["s2"])
            s3_vals.append(latest["s3"])
        elapsed = time.time() - start
        progress.progress(min(1.0, elapsed / duration), text=f"Recording trial... {elapsed:.1f}s / {duration}s")
        time.sleep(interval)
    progress.progress(1.0, text="TRIAL COMPLETE")

    if len(s1_vals) < settings["min_quality_samples"]:
        st.error(f"Insufficient samples collected ({len(s1_vals)}). Check the connection and try again.")
    else:
        summary = summarize_trial(s1_vals, s2_vals, s3_vals)
        trial_current = {
            "sensor1": summary["sensor1"]["peak_to_peak"],
            "sensor2": summary["sensor2"]["peak_to_peak"],
            "sensor3": summary["sensor3"]["peak_to_peak"],
        }
        mean_response = (summary["sensor1"]["mean"] + summary["sensor2"]["mean"] + summary["sensor3"]["mean"]) / 3
        max_response = max(summary["sensor1"]["max"], summary["sensor2"]["max"], summary["sensor3"]["max"])
        min_response = min(summary["sensor1"]["min"], summary["sensor2"]["min"], summary["sensor3"]["min"])

        if baseline_is_valid(baseline):
            result = calculate_anomaly_score(trial_current, baseline)
            status = classify_status(result["combined_score"], settings["anomaly_threshold_pct"], settings.get("urgent_threshold_pct"))
            anomaly_score = result["combined_score"]
        else:
            status = "NO BASELINE"
            anomaly_score = None

        insert_trial({
            "condition": condition,
            "sensor1": trial_current["sensor1"],
            "sensor2": trial_current["sensor2"],
            "sensor3": trial_current["sensor3"],
            "mean_response": mean_response,
            "max_response": max_response,
            "min_response": min_response,
            "anomaly_score": anomaly_score,
            "status": status,
            "data_source": app_state.data_source_label(),
        })

        st.success("TRIAL COMPLETE — recorded to history.")
        c1, c2, c3 = st.columns(3)
        c1.metric("Sensor 1 (P2P)", f"{trial_current['sensor1']:.1f}")
        c2.metric("Sensor 2 (P2P)", f"{trial_current['sensor2']:.1f}")
        c3.metric("Sensor 3 (P2P)", f"{trial_current['sensor3']:.1f}")

        if status == "NO BASELINE":
            st.info("Baseline not available yet — trial saved without an anomaly classification. Complete Baseline Calibration to enable detection.")
        else:
            color, icon = status_style(status)
            st.markdown(f"### {icon} :orange[{status}]" if status != "NORMAL" else f"### {icon} :green[{status}]")
            st.caption(f"Combined anomaly score: {anomaly_score:.1f}%  ·  Reason: sensor response differs from baseline by this amount.")

st.divider()
disclaimer()
