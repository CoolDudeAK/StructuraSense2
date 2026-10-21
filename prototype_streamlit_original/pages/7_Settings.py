"""
Settings — serial, experiment, detection, and data configuration.
"""
import streamlit as st

from config import load_settings, save_settings
from serial_reader import list_ports
from state import get_app_state
from ui_helpers import inject_css, page_header

st.set_page_config(page_title="Settings · StructuraSense", page_icon="⚙️", layout="wide")
inject_css()

app_state = get_app_state()
page_header(connected=app_state.get_active_source() is not None, source_label=app_state.data_source_label())

st.title("Settings")
settings = load_settings()

st.subheader("Serial")
ports = list_ports()
options = [""] + ports
current_port = settings["com_port"] if settings["com_port"] in options else ""
com_port = st.selectbox("COM Port", options, index=options.index(current_port))
baud_rate = st.number_input("Baud Rate", min_value=300, max_value=250000, value=int(settings["baud_rate"]), step=100)

st.subheader("Experiment")
trial_duration = st.number_input("Trial Duration (seconds)", min_value=1, max_value=60, value=int(settings["trial_duration_sec"]))
sampling_interval = st.number_input("Sampling Interval (seconds)", min_value=0.01, max_value=2.0,
                                     value=float(settings["sampling_interval_sec"]), step=0.01, format="%.2f")
num_baseline_trials = st.number_input("Number of Baseline Trials", min_value=3, max_value=100,
                                       value=int(settings["num_baseline_trials"]))

st.subheader("Detection")
st.caption("Thresholds should be determined experimentally by comparing intact and damaged trials — "
           "they are not pre-validated engineering limits.")
anomaly_threshold = st.slider("Anomaly Threshold (%) — NORMAL vs POSSIBLE ANOMALY", 1.0, 100.0,
                               float(settings["anomaly_threshold_pct"]))
urgent_threshold = st.slider("Urgent Threshold (%) — POSSIBLE ANOMALY vs URGENT REVIEW", 1.0, 200.0,
                              float(settings["urgent_threshold_pct"]))
min_quality = st.number_input("Minimum Samples per Trial", min_value=1, max_value=100,
                               value=int(settings["min_quality_samples"]))

st.subheader("Data")
storage_dir = st.text_input("Storage Directory", value=settings["storage_dir"])

if st.button("💾 Save Settings", type="primary"):
    if urgent_threshold <= anomaly_threshold:
        st.error("Urgent Threshold must be greater than the Anomaly Threshold.")
    else:
        settings.update({
            "com_port": com_port,
            "baud_rate": int(baud_rate),
            "trial_duration_sec": int(trial_duration),
            "sampling_interval_sec": float(sampling_interval),
            "num_baseline_trials": int(num_baseline_trials),
            "anomaly_threshold_pct": float(anomaly_threshold),
            "urgent_threshold_pct": float(urgent_threshold),
            "min_quality_samples": int(min_quality),
            "storage_dir": storage_dir,
        })
        save_settings(settings)
        st.success("Settings saved.")
