"""
About — project positioning, prototype scope, and honest limitations.
"""
import streamlit as st

from state import get_app_state
from ui_helpers import inject_css, page_header

st.set_page_config(page_title="About · StructuraSense", page_icon="ℹ️", layout="wide")
inject_css()

app_state = get_app_state()
page_header(connected=app_state.get_active_source() is not None, source_label=app_state.data_source_label())

st.title("About StructuraSense")
st.caption("Team NexaStruc · MSME 6.0 Hackathon cum Start-up Contest")

st.markdown(
    "StructuraSense is an AI-assisted structural health monitoring concept designed to move "
    "infrastructure monitoring toward continuous, data-driven and condition-based assessment."
)

st.subheader("Current Prototype")
st.code(
    "Piezo Sensors\n"
    "  ↓\n"
    "Arduino UNO\n"
    "  ↓\n"
    "Signal Processing\n"
    "  ↓\n"
    "Baseline Analysis\n"
    "  ↓\n"
    "Anomaly Detection\n"
    "  ↓\n"
    "Dashboard",
    language="text",
)

st.subheader("Prototype System Diagram")
st.code(
    "┌──────────────────┐\n"
    "│ CONCRETE BLOCK   │\n"
    "└────────┬─────────┘\n"
    "         ▼\n"
    "┌──────────────────┐\n"
    "│ 3 PIEZO SENSORS  │\n"
    "└────────┬─────────┘\n"
    "         ▼\n"
    "┌──────────────────┐\n"
    "│ ARDUINO UNO      │\n"
    "└────────┬─────────┘\n"
    "         │ USB\n"
    "         ▼\n"
    "┌──────────────────┐\n"
    "│ COMPUTER         │\n"
    "│ STRUCTURASENSE   │\n"
    "└────────┬─────────┘\n"
    "         ▼\n"
    "┌──────────────────┐\n"
    "│ SIGNAL PROCESSING│\n"
    "└────────┬─────────┘\n"
    "         ▼\n"
    "┌──────────────────┐\n"
    "│ ANOMALY ENGINE   │\n"
    "└────────┬─────────┘\n"
    "         ▼\n"
    "┌──────────────────┐\n"
    "│ DASHBOARD        │\n"
    "└──────────────────┘",
    language="text",
)

st.divider()
st.subheader("Where this fits in the broader StructuraSense platform")
st.markdown(
    "The pitch deck describes a four-layer production architecture — Data Acquisition, "
    "Intelligence, Processing, and Reporting — combining vision (CCTV/drone), structural "
    "sensors (strain gauges, accelerometers, LVDTs), and low-cost physics devices (piezo, "
    "tuning forks) into a Structural Health Index."
)

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Current prototype**")
    st.markdown("- Piezo sensors ×3\n- Arduino UNO\n- Laptop\n- Rule-based anomaly detection")
with col2:
    st.markdown("**Future / production vision**")
    st.markdown(
        "- CCTV / drone vision + CNN/YOLO crack detection\n"
        "- Accelerometers, strain gauges, load, temperature sensors\n"
        "- AI/ML models (Random Forest, LSTM, Autoencoder)\n"
        "- Cloud dashboard & structural health index"
    )

st.caption("Health-score bands referenced in the pitch deck: 80–100 Optimal · 60–80 Routine check · "
           "40–60 Inspection needed · below 40 Urgent repair. This prototype's threshold-based "
           "NORMAL / POSSIBLE ANOMALY / URGENT REVIEW status is a simplified proof-of-concept "
           "approximation of that framework, based only on piezo vibration response.")

st.divider()
st.error(
    "**Important:** Current prototype is a proof-of-concept and is not a replacement for "
    "professional structural inspection. It does not detect exact crack width or depth, does "
    "not certify structural safety, and is not validated for bridge-scale deployment."
)

st.caption("Team NexaStruc — MSME 6.0 Hackathon cum Start-up Contest.")
