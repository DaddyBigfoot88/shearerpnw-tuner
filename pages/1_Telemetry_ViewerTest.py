import streamlit as st
import requests
import json
from io import BytesIO

st.set_page_config(page_title="IBT Uploader + Export", layout="wide")
st.title("IBT Reader • Export for ChatGPT")

st.markdown(
    "Upload an **.ibt** file, choose your channels, and I’ll give you a CSV and a ChatGPT-ready JSON summary."
)

# API base (change if you host it elsewhere)
API_BASE = st.secrets.get("IBT_API_BASE", "http://localhost:3080")

# default channel list (you can tweak)
default_channels = "Lap, LapDistPct, Speed, Throttle, Brake, Clutch, Gear, RPM, SteeringWheelAngle, LatAccel, LongAccel, TrackTemp, FuelLevel"

channels = st.text_input("Channels (comma-separated)", value=default_channels)
uploaded = st.file_uploader("Drop your .ibt file", type=["ibt"])

col_a, col_b = st.columns([1,1])

with col_a:
    st.caption("Tip: keep channel list short for faster exports.")
with col_b:
    run_btn = st.button("Process IBT", type="primary", disabled=uploaded is None)

if run_btn and uploaded:
    with st.spinner("Uploading to parser…"):
        try:
            files = {
                "ibt": (uploaded.name, uploaded.getvalue(), "application/octet-stream")
            }
            data = {"channels": channels}
            resp = requests.post(f"{API_BASE}/api/ibt/upload", files=files, data=data, timeout=120)

            if resp.status_code != 200:
                st.error(f"Server error: {resp.status_code} — {resp.text[:300]}")
            else:
                out = resp.json()
                if not out.get("ok"):
                    st.error(f"Parser error: {out.get('error','unknown error')}")
                else:
                    st.success("Done! Grab your files below.")

                    # Download links
                    st.markdown("### Downloads")
                    dl_col1, dl_col2 = st.columns(2)
                    with dl_col1:
                        st.link_button("⬇️ Download CSV", f"{API_BASE}{out['csv']}", use_container_width=True)
                    with dl_col2:
                        st.link_button("⬇️ Download ChatGPT JSON", f"{API_BASE}{out['summary']}", use_container_width=True)

                    # Show quick meta + channels
                    st.markdown("### Info")
                    st.json({
                        "file": out.get("info",{}).get("file"),
                        "tickRateHz": out.get("info",{}).get("tickRateHz"),
                        "channels": out.get("channels", [])
                    })

                    # Also fetch and preview first part of JSON summary
                    try:
                        sresp = requests.get(f"{API_BASE}{out['summary']}", timeout=60)
                        if sresp.ok:
                            summary = sresp.json()
                            st.markdown("### Summary Preview")
                            st.write(summary.get("plainSummary"))
                            with st.expander("Lap stats (first 25)"):
                                st.json(summary.get("laps", [])[:25])
                    except Exception as e:
                        st.info("Couldn’t preview JSON summary (still downloadable).")

        except requests.exceptions.ConnectionError:
            st.error("Can’t reach the IBT API. Make sure your Node server is running on :3080.")
        except Exception as e:
            st.exception(e)
