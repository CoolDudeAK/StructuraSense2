"""
ui_helpers.py
-------------
Small shared UI building blocks so every page looks consistent:
clean, technical, professional — suitable for an infrastructure
monitoring platform, not a flashy consumer app.
"""

import streamlit as st

PRIMARY = "#0F4C5C"       # deep engineering teal
NORMAL_COLOR = "#1B8A5A"  # green
WARNING_COLOR = "#C97A0C" # amber
URGENT_COLOR = "#B3261E"  # red
MUTED = "#6B7280"

BASE_CSS = """
<style>
    .ss-header {
        display: flex; justify-content: space-between; align-items: baseline;
        border-bottom: 2px solid #E5E7EB; padding-bottom: 0.6rem; margin-bottom: 1rem;
    }
    .ss-title { font-size: 1.7rem; font-weight: 700; letter-spacing: 0.02em; color: #111827; }
    .ss-subtitle { font-size: 0.95rem; color: #6B7280; margin-top: -0.3rem; }
    .status-dot { font-size: 1rem; font-weight: 600; }
    .ss-card {
        border: 1px solid #E5E7EB; border-radius: 10px; padding: 1.1rem 1.3rem;
        background-color: #FAFBFC;
    }
    .ss-metric-label { font-size: 0.8rem; color: #6B7280; text-transform: uppercase; letter-spacing: 0.04em; }
    .ss-metric-value { font-size: 1.6rem; font-weight: 700; color: #111827; }
    .ss-banner-demo {
        background-color: #FFF3CD; color: #7A5B00; border: 1px solid #FFE29A;
        border-radius: 8px; padding: 0.6rem 1rem; font-weight: 600; margin-bottom: 1rem;
    }
    .ss-banner-live {
        background-color: #E7F6EC; color: #14532D; border: 1px solid #BBE8CC;
        border-radius: 8px; padding: 0.6rem 1rem; font-weight: 600; margin-bottom: 1rem;
    }
    .ss-banner-none {
        background-color: #F3F4F6; color: #4B5563; border: 1px solid #E5E7EB;
        border-radius: 8px; padding: 0.6rem 1rem; font-weight: 600; margin-bottom: 1rem;
    }
</style>
"""


def inject_css():
    st.markdown(BASE_CSS, unsafe_allow_html=True)


def page_header(connected: bool, source_label: str = ""):
    dot_color = NORMAL_COLOR if connected else MUTED
    status_text = "● CONNECTED" if connected else "● DISCONNECTED"
    st.markdown(
        f"""
        <div class="ss-header">
            <div>
                <div class="ss-title">STRUCTURASENSE</div>
                <div class="ss-subtitle">AI-Assisted Structural Health Monitoring</div>
            </div>
            <div class="status-dot" style="color:{dot_color}">{status_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if source_label == "DEMO/SIMULATION DATA":
        st.markdown('<div class="ss-banner-demo">⚠ DEMO MODE — SIMULATED DATA. Not real sensor readings.</div>', unsafe_allow_html=True)
    elif source_label == "LIVE HARDWARE DATA":
        st.markdown('<div class="ss-banner-live">● LIVE HARDWARE DATA — reading from connected Arduino.</div>', unsafe_allow_html=True)
    elif source_label == "NO DATA SOURCE":
        st.markdown('<div class="ss-banner-none">No active data source. Connect the Arduino (Device page) or start Demo Mode.</div>', unsafe_allow_html=True)


def status_style(status: str):
    if status == "NORMAL":
        return NORMAL_COLOR, "✓"
    if status == "POSSIBLE ANOMALY":
        return WARNING_COLOR, "⚠"
    if status == "URGENT REVIEW":
        return URGENT_COLOR, "⛔"
    return MUTED, "…"


def health_status_card(status: str, health_score: float):
    color, icon = status_style(status)
    st.markdown(
        f"""
        <div class="ss-card" style="text-align:center; border-color:{color}33; background-color:{color}0D;">
            <div class="ss-metric-label">STRUCTURAL HEALTH STATUS</div>
            <div style="font-size:2.2rem; font-weight:800; color:{color}; margin:0.3rem 0;">{icon} {status}</div>
            <div class="ss-metric-label" style="margin-top:0.6rem;">Prototype Health Score</div>
            <div style="font-size:2.5rem; font-weight:800; color:{color};">{health_score:.0f}%</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sensor_card(name: str, current, baseline, deviation):
    if baseline is None:
        st.markdown(
            f"""
            <div class="ss-card">
                <div class="ss-metric-label">{name}</div>
                <div class="ss-metric-value">{current:.1f}</div>
                <div style="color:#9CA3AF;">Baseline not set</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return
    dev_color = NORMAL_COLOR if deviation < 15 else (WARNING_COLOR if deviation < 40 else URGENT_COLOR)
    st.markdown(
        f"""
        <div class="ss-card">
            <div class="ss-metric-label">{name}</div>
            <div class="ss-metric-value">{current:.1f}</div>
            <div style="color:#6B7280; font-size:0.85rem;">Baseline: {baseline:.1f}</div>
            <div style="color:{dev_color}; font-weight:700;">Deviation: {deviation:.1f}%</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def disclaimer():
    st.caption(
        "⚠️ Prototype limitation: this system identifies changes in measured vibration response. "
        "It does not detect exact crack width/depth, does not certify structural safety, and does "
        "not replace professional structural inspection."
    )
