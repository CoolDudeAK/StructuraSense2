"""
Data Analysis — compare intact vs damaged trial statistics.
"""
import pandas as pd
import streamlit as st

from data_storage import get_all_trials
from ui_helpers import inject_css, page_header
from state import get_app_state

st.set_page_config(page_title="Analysis · StructuraSense", page_icon="📊", layout="wide")
inject_css()

app_state = get_app_state()
page_header(connected=app_state.get_active_source() is not None, source_label=app_state.data_source_label())

st.title("Data Analysis")
st.caption("Compare intact vs. damaged specimen responses across recorded trials.")

trials = get_all_trials()
if not trials:
    st.info("No trials recorded yet. Run trials on the Experiment page first.")
    st.stop()

df = pd.DataFrame(trials)

intact = df[df["condition"] == "Intact"]
damaged = df[df["condition"] == "Damaged"]

st.subheader("Intact vs Damaged — Sensor Response")
for i in (1, 2, 3):
    col = f"sensor{i}"
    st.markdown(f"**Sensor {i}**")
    chart_df = pd.DataFrame({
        "Intact": intact[col].reset_index(drop=True),
        "Damaged": damaged[col].reset_index(drop=True),
    })
    st.bar_chart(chart_df, height=220)

st.divider()
st.subheader("Summary Statistics")

def summarize(sub_df, label):
    rows = []
    for i in (1, 2, 3):
        col = f"sensor{i}"
        vals = sub_df[col].dropna()
        rows.append({
            "Condition": label,
            "Sensor": f"Piezo {i}",
            "Mean": round(vals.mean(), 2) if len(vals) else None,
            "Std Dev": round(vals.std(), 2) if len(vals) > 1 else None,
            "Trials": len(vals),
        })
    return rows

summary_rows = summarize(intact, "Intact") + summarize(damaged, "Damaged")
st.dataframe(pd.DataFrame(summary_rows), hide_index=True, width='stretch')

st.divider()
st.subheader("Percentage Deviation & Trial-to-Trial Variability")
if len(intact) > 0 and len(damaged) > 0:
    rows = []
    for i in (1, 2, 3):
        col = f"sensor{i}"
        intact_mean = intact[col].mean()
        damaged_mean = damaged[col].mean()
        pct_dev = abs(damaged_mean - intact_mean) / intact_mean * 100 if intact_mean else None
        rows.append({
            "Sensor": f"Piezo {i}",
            "Intact Mean": round(intact_mean, 2),
            "Damaged Mean": round(damaged_mean, 2),
            "% Deviation (Damaged vs Intact)": round(pct_dev, 1) if pct_dev is not None else "—",
            "Intact Std Dev": round(intact[col].std(), 2) if len(intact) > 1 else "—",
            "Damaged Std Dev": round(damaged[col].std(), 2) if len(damaged) > 1 else "—",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
else:
    st.caption("Record trials under both Intact and Damaged conditions to see comparative deviation statistics.")

st.divider()
st.subheader("Anomaly Score Distribution")
score_df = df[["condition", "anomaly_score"]].dropna()
if not score_df.empty:
    st.bar_chart(score_df.set_index(score_df.index)["anomaly_score"], height=220)
else:
    st.caption("No anomaly scores available yet (requires a saved baseline at the time trials were recorded).")
