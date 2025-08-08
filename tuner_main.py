import streamlit as st
import json
import os

st.set_page_config(page_title="ShearerPNW Easy Tuner", layout="wide")

st.title("ShearerPNW Easy Tuner")
st.subheader("NASCAR Next Gen • Feedback-Based Setup Assistant")

# Hint to find the Telemetry page in the sidebar
with st.sidebar:
    st.success("Need charts or a ChatGPT export? Go to **Pages → Telemetry Viewer**.")

# === Load Corner Feedback Rules ===
RULES_PATH = "ShearerPNW_Easy_Tuner_Editables/track_corner_rules.json"
corner_rules = {}
if os.path.exists(RULES_PATH):
    with open(RULES_PATH, "r") as f:
        corner_rules = json.load(f)
else:
    st.warning("track_corner_rules.json not found. Using a tiny demo so the UI works.")
    corner_rules = {
        "Watkins Glen International": {
            "baseline_temp": 85,
            "T1": {
                "rules": {
                    "Loose on entry": {
                        "slight": [
                            "➤ Add 1 click RF LS rebound",
                            "➤ Increase RF tire pressure by 0.5 psi",
                            "➤ Raise crossweight by 0.3%"
                        ],
                        "moderate": [
                            "➤ Add 2 clicks RF LS rebound",
                            "➤ Increase RF tire pressure by 1.0 psi",
                            "➤ Raise crossweight by 0.5%"
                        ],
                        "severe": [
                            "➤ Add 3 clicks RF LS rebound",
                            "➤ Increase RF tire pressure by 1.5 psi",
                            "➤ Raise crossweight by 0.8%"
                        ]
                    }
                }
            },
            "T2": {
                "rules": {
                    "Loose on exit": {
                        "slight": [
                            "➤ Soften RR HS bump 1 click",
                            "➤ Increase RR tire pressure by 0.5 psi"
                        ],
                        "moderate": [
                            "➤ Soften RR HS bump 2 clicks",
                            "➤ Increase RR tire pressure by 1.0 psi"
                        ],
                        "severe": [
                            "➤ Soften RR HS bump 3 clicks",
                            "➤ Increase RR tire pressure by 1.5 psi",
                            "➤ Raise crossweight by 0.5%"
                        ]
                    }
                }
            }
        }
    }

# === Track (locked for now) ===
track = "Watkins Glen International"
st.text(f"Track locked: {track}")

def list_corners(track_dict):
    # everything except baseline_temp is a corner key
    return [k for k in track_dict.keys() if k != "baseline_temp"]

track_data = corner_rules.get(track, {})
corner_choices = list_corners(track_data) if isinstance(track_data, dict) else []
if not corner_choices:
    st.error("No corners found in track_corner_rules.json for this track.")
    st.stop()

# === Corner, Feedback, Severity ===
corner = st.selectbox("Select Track Corner", corner_choices)
feedback = st.selectbox(
    "How does the car feel?",
    [
        "Loose on entry", "Loose mid-corner", "Loose on exit",
        "Tight on entry", "Tight mid-corner", "Tight on exit"
    ]
)
severity_level = st.slider("How bad is it?", 1, 10, 5)
severity = "slight" if severity_level <= 3 else ("moderate" if severity_level <= 7 else "severe")

# === Temperature Comparison ===
st.markdown("### 🌡️ Track Temperature Adjustment Mode")
temp_only = st.checkbox("Show adjustments for temperature difference only")

current_temp = st.slider("Current Track Temperature (°F)", 60, 140, 90)
baseline_temp = int(track_data.get("baseline_temp", 85)) if isinstance(track_data, dict) else 85
baseline_temp = st.slider("Baseline Setup Temperature (°F)", 60, 140, baseline_temp)
temp_diff = current_temp - baseline_temp

if temp_only:
    st.markdown("### 🔧 Temperature-Based Adjustment Suggestions")
    if abs(temp_diff) > 5:
        if temp_diff > 0:
            st.warning(f"Track is {temp_diff}°F hotter than baseline. Expect reduced grip.")
            st.write("- Lower tire pressures by 0.5–1.5 psi")
            st.write("- Stiffen shocks slightly to control excess movement")
            st.write("- Consider a touch more rear spring or diff preload (within limits)")
        else:
            st.info(f"Track is {abs(temp_diff)}°F cooler than baseline. More grip, less pressure build.")
            st.write("- Raise tire pressures by 0.5–1.5 psi")
            st.write("- Soften rear shocks slightly for added rotation")
            st.write("- May reduce preload or raise RR ride height a tick")
    else:
        st.success("Track temp is close to baseline. No major adjustments needed.")
else:
    st.markdown("## 🧠 Setup Adjustment Suggestions")
    corner_data = track_data.get(corner, {}) if isinstance(track_data, dict) else {}
    rules_data = corner_data.get("rules", {}) if isinstance(corner_data, dict) else {}
    feedback_data = rules_data.get(feedback, {}) if isinstance(rules_data, dict) else {}
    tips = feedback_data.get(severity, []) if isinstance(feedback_data, dict) else []

    if tips:
        for tip in tips:
            st.write(tip)
    else:
        st.info("No suggestions for that symptom at this corner/severity.")

# === Placeholder for setup entry (will move to its own page later) ===
st.markdown("## ⚙️ Current Setup (Manual Input Placeholder)")
st.info("For telemetry upload, graphs, and the ChatGPT export block, use **Pages → Telemetry Viewer** in the sidebar.")

st.markdown("---")
st.caption("ShearerPNW Easy Tuner – v1.2 Corner Logic Engine")
