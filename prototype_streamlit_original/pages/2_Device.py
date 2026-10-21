"""
Device — connect to the Arduino UNO over USB serial.
"""
import streamlit as st

from config import load_settings, save_settings
from serial_reader import list_ports
from state import get_app_state
from ui_helpers import inject_css, page_header

st.set_page_config(page_title="Device · StructuraSense", page_icon="🔌", layout="wide")
inject_css()

app_state = get_app_state()
settings = load_settings()
reader = app_state.serial_reader

page_header(connected=app_state.get_active_source() is not None, source_label=app_state.data_source_label())

st.title("Device Connection")
st.caption("Connect StructuraSense to the Arduino UNO carrying the 3 piezo sensor channels.")

if reader.is_connected:
    st.success(f"✓ Arduino UNO Connected — {reader.port} @ {reader.baud_rate} baud")
else:
    st.info("Arduino Status: **DISCONNECTED**")

col1, col2 = st.columns([2, 1])

with col1:
    if st.button("🔄 Refresh Ports"):
        st.rerun()

    ports = list_ports()
    if ports:
        default_index = ports.index(settings["com_port"]) if settings["com_port"] in ports else 0
        selected_port = st.selectbox("Available COM Ports", ports, index=default_index)
    else:
        st.warning("No COM ports detected. Make sure the Arduino is plugged in via USB, then click Refresh Ports.")
        selected_port = None

    baud_rate = st.number_input("Baud Rate", min_value=300, max_value=250000, value=settings["baud_rate"], step=100)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔌 Connect", type="primary", disabled=(selected_port is None), width='stretch'):
            ok, msg = reader.connect(selected_port, int(baud_rate))
            if ok:
                app_state.active_source = "live"
                app_state.demo_generator.stop()
                settings["com_port"] = selected_port
                settings["baud_rate"] = int(baud_rate)
                save_settings(settings)
                st.success(msg)
            else:
                st.error(msg)
            st.rerun()
    with c2:
        if st.button("⏻ Disconnect", width='stretch'):
            reader.disconnect()
            if app_state.active_source == "live":
                app_state.active_source = "none"
            st.rerun()

with col2:
    st.markdown("#### What to do next")
    st.markdown(
        "1. Plug the Arduino UNO into a USB port.\n"
        "2. Click **Refresh Ports**.\n"
        "3. Select the correct COM port.\n"
        "4. Click **Connect**.\n"
        "5. Go to the **Experiment** page to run a trial."
    )

st.divider()
st.subheader("Serial Monitor")
st.caption("Raw incoming data — useful for confirming the Arduino is sending the expected format.")

with st.expander("RAW SERIAL DATA", expanded=True):
    raw_log = reader.get_raw_log()
    if raw_log:
        st.code("\n".join(raw_log[-40:]), language="text")
    else:
        st.markdown("_No data received yet._")
    err = reader.get_last_error()
    if err:
        st.error(f"Invalid sensor packet received: {err}")
    if st.button("Clear Serial Log"):
        reader.clear_raw_log()
        st.rerun()

st.caption("Expected packet formats: `S1:184,S2:126,S3:171`  or  `184,126,171`")
