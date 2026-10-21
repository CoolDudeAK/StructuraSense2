"""
Dashboard — main real-time monitoring interface.
"""
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from anomaly_detection import calculate_anomaly_score, classify_status
from baseline import baseline_is_valid, load_baseline
from config import load_settings
from state import get_app_state
from ui_helpers import (disclaimer, health_status_card, inject_css,
                         page_header, sensor_card)

st.set_page_config(page_title="Dashboard · StructuraSense", page_icon="🏗️", layout="wide")
inject_css()

app_state = get_app_state()
settings = load_settings()
baseline = load_baseline()

source = app_state.get_active_source()
source_label = app_state.data_source_label()

page_header(connected=source is not None, source_label=source_label)

st.sidebar.title("StructuraSense")
st.sidebar.caption("Team NexaStruc · MSME 6.0 Hackathon")

# Auto-refresh the dashboard every second so live readings/graphs update
# without the user having to click anything.
st_autorefresh(interval=1000, key="dashboard_autorefresh")

latest = source.get_latest() if source else None
buffer = source.get_buffer() if source else []

col_status, col_sensors = st.columns([1, 2])

if not baseline_is_valid(baseline):
    with col_status:
        st.warning("Baseline not available.\n\nPlease perform calibration before anomaly detection.", icon="⚠️")
    status, health_score = "—", 0
    deviations = {"sensor1": 0, "sensor2": 0, "sensor3": 0}
elif latest is None:
    with col_status:
        st.info("Waiting for sensor data...", icon="⏳")
    status, health_score = "—", 0
    deviations = {"sensor1": 0, "sensor2": 0, "sensor3": 0}
else:
    current = {"sensor1": latest["s1"], "sensor2": latest["s2"], "sensor3": latest["s3"]}
    result = calculate_anomaly_score(current, baseline)
    status = classify_status(
        result["combined_score"],
        settings["anomaly_threshold_pct"],
        settings.get("urgent_threshold_pct"),
    )
    health_score = result["health_score"]
    deviations = result["deviations"]
    with col_status:
        health_status_card(status, health_score)

with col_sensors:
    if latest is not None:
        s1, s2, s3 = st.columns(3)
        b1 = baseline.get("sensor1_mean") if baseline else None
        b2 = baseline.get("sensor2_mean") if baseline else None
        b3 = baseline.get("sensor3_mean") if baseline else None
        with s1:
            sensor_card("PIEZO SENSOR 1", latest["s1"], b1, deviations.get("sensor1", 0))
        with s2:
            sensor_card("PIEZO SENSOR 2", latest["s2"], b2, deviations.get("sensor2", 0))
        with s3:
            sensor_card("PIEZO SENSOR 3", latest["s3"], b3, deviations.get("sensor3", 0))
    else:
        st.markdown("No live readings yet. Connect the Arduino on the **Device** page, or start **Demo Mode** below.")

st.divider()

# ---------------- Live graph ----------------
st.subheader("Live Vibration Response")

g1, g2, g3, g4 = st.columns([1, 1, 1, 3])
with g1:
    paused = st.toggle("Pause", key="graph_paused")
with g2:
    if st.button("Clear graph"):
        if source:
            source.clear_buffer()
        st.rerun()
with g3:
    window = st.selectbox("Window", [50, 100, 200, 500], index=1, label_visibility="collapsed")

if buffer and not paused:
    df = pd.DataFrame(buffer[-window:])
    df = df.rename(columns={"s1": "Sensor 1", "s2": "Sensor 2", "s3": "Sensor 3"})
    df = df.set_index("timestamp")[["Sensor 1", "Sensor 2", "Sensor 3"]]
    st.line_chart(df, height=320)
else:
    st.markdown(
        "<div style='height:200px; display:flex; align-items:center; justify-content:center; "
        "color:#9CA3AF; border:1px dashed #E5E7EB; border-radius:8px;'>"
        + ("Graph paused." if paused else "Waiting for sensor data...")
        + "</div>",
        unsafe_allow_html=True,
    )

st.divider()

# ---------------- Baseline vs current + Alerts ----------------
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Baseline vs Current")
    if baseline_is_valid(baseline) and latest is not None:
        rows = []
        for i, key in enumerate(["sensor1", "sensor2", "sensor3"], start=1):
            rows.append({
                "Sensor": f"Piezo {i}",
                "Baseline": round(baseline[f"{key}_mean"], 1),
                "Current": round(latest[f"s{i}"], 1),
                "Deviation %": round(deviations[key], 1),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        largest = max(deviations, key=deviations.get)
        largest_num = {"sensor1": 1, "sensor2": 2, "sensor3": 3}[largest]
        st.caption(f"Largest deviation: **PIEZO SENSOR {largest_num}** ({deviations[largest]:.1f}%). "
                   "This indicates the sensor whose response differs most from baseline — not an exact crack location.")
    else:
        st.info("Comparison will appear once a baseline is saved and live data is available.")

with col_b:
    st.subheader("Alerts")
    if status == "NORMAL":
        st.success("✓ System operating normally")
    elif status == "POSSIBLE ANOMALY":
        largest = max(deviations, key=deviations.get) if deviations else None
        largest_num = {"sensor1": 1, "sensor2": 2, "sensor3": 3}.get(largest, "?")
        st.warning(
            f"⚠ POSSIBLE ANOMALY\n\n"
            f"Sensor {largest_num} response differs from baseline.\n\n"
            f"**Recommended action:** perform visual/engineering inspection.",
        )
    elif status == "URGENT REVIEW":
        st.error(
            "⛔ URGENT REVIEW\n\n"
            "Deviation from baseline substantially exceeds the configured threshold.\n\n"
            "**Recommended action:** prioritize immediate visual/engineering inspection."
        )
    else:
        st.markdown("_No status available yet._")

st.divider()

# ---------------- Demo mode controls ----------------
with st.expander("🎮 Demo Mode (use when Arduino is disconnected)", expanded=(source is None)):
    st.caption("Generates clearly labelled simulated data so the app can be demonstrated without hardware.")
    d1, d2, d3 = st.columns(3)
    with d1:
        if st.button("▶ Simulate NORMAL", width='stretch'):
            app_state.demo_generator.set_scenario("normal")
            app_state.demo_generator.start(baseline=baseline)
            app_state.active_source = "demo"
            st.rerun()
    with d2:
        if st.button("▶ Simulate ANOMALY", width='stretch'):
            app_state.demo_generator.set_scenario("anomaly")
            app_state.demo_generator.start(baseline=baseline)
            app_state.active_source = "demo"
            st.rerun()
    with d3:
        if st.button("■ Stop Demo Mode", width='stretch'):
            app_state.demo_generator.stop()
            if app_state.active_source == "demo":
                app_state.active_source = "none"
            st.rerun()

st.divider()
disclaimer()
