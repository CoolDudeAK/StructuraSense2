"""
app.py
------
StructuraSense — main entry point.

Run with:
    streamlit run app.py

This file only sets global page config and lands the user on the
Dashboard. All actual pages live in pages/ and are auto-discovered by
Streamlit's multipage navigation (sidebar on the left).
"""

import streamlit as st

st.set_page_config(
    page_title="StructuraSense",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Touch the shared app state once at startup so the serial reader /
# demo generator singleton is created before any page needs it.
from state import get_app_state  # noqa: E402
from data_storage import init_db  # noqa: E402

get_app_state()
init_db()

st.switch_page("pages/1_Dashboard.py")
