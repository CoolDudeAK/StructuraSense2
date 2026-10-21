"""
Experiment History — full trial log with filters and CSV export.
"""
import os

import pandas as pd
import streamlit as st

from config import load_settings
from data_storage import delete_all_trials, export_csv, get_all_trials
from state import get_app_state
from ui_helpers import inject_css, page_header

st.set_page_config(page_title="History · StructuraSense", page_icon="🗂️", layout="wide")
inject_css()

app_state = get_app_state()
page_header(connected=app_state.get_active_source() is not None, source_label=app_state.data_source_label())

st.title("Experiment History")

f1, f2, f3 = st.columns(3)
with f1:
    condition_filter = st.selectbox("Condition", ["All", "Intact", "Damaged"])
with f2:
    status_filter = st.selectbox("Status", ["All", "NORMAL", "POSSIBLE ANOMALY", "URGENT REVIEW", "NO BASELINE"])
with f3:
    st.write("")
    st.write("")
    if st.button("🗑 Clear All History"):
        st.session_state["confirm_clear"] = True

if st.session_state.get("confirm_clear"):
    st.warning("This will permanently delete all recorded trials.")
    cc1, cc2 = st.columns(2)
    if cc1.button("Yes, delete everything", type="primary"):
        delete_all_trials()
        st.session_state["confirm_clear"] = False
        st.rerun()
    if cc2.button("Cancel"):
        st.session_state["confirm_clear"] = False
        st.rerun()

trials = get_all_trials(condition_filter=condition_filter, status_filter=status_filter)

if not trials:
    st.info("No trials match the current filters.")
else:
    df = pd.DataFrame(trials)
    display_df = df.rename(columns={
        "id": "Trial", "timestamp": "Date/Time", "condition": "Condition",
        "sensor1": "S1", "sensor2": "S2", "sensor3": "S3",
        "anomaly_score": "Score", "status": "Status", "data_source": "Source",
    })[["Trial", "Date/Time", "Condition", "S1", "S2", "S3", "Score", "Status", "Source"]]
    st.dataframe(display_df, hide_index=True, width='stretch')

    st.caption(f"{len(trials)} trial(s) shown.")

st.divider()
st.subheader("Export")
settings = load_settings()
export_path = os.path.join(settings["storage_dir"], "structurasense_export.csv")
if st.button("⬇ Export CSV"):
    path = export_csv(export_path)
    with open(path, "rb") as f:
        st.download_button("Download CSV file", f, file_name="structurasense_trials.csv", mime="text/csv")
    st.success(f"Exported {len(get_all_trials())} trials.")
