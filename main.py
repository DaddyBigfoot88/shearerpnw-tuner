import streamlit as st
import json
import os

# === SECTION: Access Control ===
if st.text_input("Enter Access Code") != "Shearer":
    st.stop()

st.title("ShearerPNW Easy Tuner")
st.subheader("NASCAR Next Gen Feedback-Based Setup Assistant")

# === SECTION: Load Corner Feedback Rules ===
corner_rules_path = "ShearerPNW_Easy_Tuner_Editables/track_corner_rules.json"
corner_rules = {}
if os.path.exists(corner_rules_path):
    with open(corner_rules_path) as f:
        corner_rules = json.load(f)

# === SECTION: Track, Corner, Feedback ===
track = st.selectbox("Select Track", list(corner_rules.keys()))
corner = st.selectbox("Select Track Corner", list(corner_rules.get(track, {}).keys()))
feedback = st.selectbox("How does the car feel?", [
    "Loose on entry", "Loose mid-corner", "Loose on exit",
    "Tight on entry", "Tight mid-corner", "Tight on exit"
])
severity_level = st.slider("How bad is it?", 1, 10, 5)
if severity_level <= 3:
    severity = "slight"
elif severity_level <= 7:
    severity = "moderate"
else:
    severity = "severe"

# === SECTION: Track Temperature Comparison ===
current_temp = st.slider("Track Temperature (°F)", 60, 140, 90)
baseline_temp = corner_rules[track].get("baseline_temp", 85)
temp_diff = current_temp - baseline_temp

if abs(temp_diff) > 10:
    if temp_diff > 0:
        st.warning(f"Track is {temp_diff}°F hotter than setup baseline. Expect reduced grip, especially rear.")
    else:
        st.info(f"Track is {abs(temp_diff)}°F cooler than baseline. Expect more initial grip, lower tire pressure buildup.")

# === SECTION: Show Adjustment Suggestions ===
st.markdown("## 🧠 Setup Adjustment Suggestions")
tips = corner_rules.get(track, {}).get(corner, {}).get("rules", {}).get(feedback, {}).get(severity, [])
if tips:
    for tip in tips:
        st.write(tip)
else:
    st.info("No suggestions available for this symptom at this corner.")

# === SECTION: Placeholder for Manual Setup Input ===
st.markdown("## ⚙️ Current Setup (Manual Input Placeholder)")
st.info("Setup entry and telemetry upload coming soon.")

# === SECTION: Footer ===
st.markdown("---")
st.caption("ShearerPNW Easy Tuner – v1.2 Corner Logic Engine")
