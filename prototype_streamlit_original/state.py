"""
state.py
--------
Streamlit reruns the entire script on every interaction, which would
normally destroy live objects like an open serial connection or a
running background thread. This module uses st.cache_resource to create
ONE long-lived AppState object shared by every page for the life of the
running app process (i.e. as long as `streamlit run app.py` is up).

Anything that must survive reruns (SerialReader, DemoGenerator, in-memory
calibration progress) lives here. Anything page-local (form inputs, UI
toggles) stays in st.session_state as usual.
"""

import streamlit as st

from serial_reader import SerialReader
from demo_mode import DemoGenerator


class AppState:
    def __init__(self):
        self.serial_reader = SerialReader()
        self.demo_generator = DemoGenerator()
        # "live" -> use serial_reader, "demo" -> use demo_generator, "none" -> no active source
        self.active_source = "none"
        # in-progress baseline calibration trials (list of dicts: sensor1/2/3)
        self.calibration_trials = []

    def get_active_source(self):
        """Return whichever data source object is currently active, or None."""
        if self.active_source == "live" and self.serial_reader.is_connected:
            return self.serial_reader
        if self.active_source == "demo" and self.demo_generator.is_connected:
            return self.demo_generator
        return None

    def data_source_label(self):
        src = self.get_active_source()
        if src is None:
            return "NO DATA SOURCE"
        return "LIVE HARDWARE DATA" if self.active_source == "live" else "DEMO/SIMULATION DATA"


@st.cache_resource
def get_app_state() -> AppState:
    return AppState()
