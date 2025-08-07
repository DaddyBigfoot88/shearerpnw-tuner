import streamlit as st
import json
import os

# 🔒 Access Control
if st.text_input("Enter Access Code") != "Shearer":
    st.stop()

st.title("ShearerPNW Easy Tuner")
st.subheader("NASCAR Next Gen Setup Input + Feedback")

# 📥 Load Track-Corner Rules
corner_rules_path = "ShearerPNW_Easy_Tuner_Editables/track_corner_rules.json"
corner_rules = {}
if os.path.exists(corner_rules_path):
    with open(corner_rules_path) as f:
        corner_rules = json.load(f)

# === Track Selection ===
track = st.selectbox("Select Track", list(corner_rules.keys()))
corner = st.selectbox("Select Track Corner", list(corner_rules.get(track, {}).keys()))
feedback = st.selectbox("How does the car feel?", [
    "Loose on entry", "Loose mid-corner", "Loose on exit",
    "Tight on entry", "Tight mid-corner", "Tight on exit",
    "Bouncy mid-corner", "Hits bump and loses control",
    "Understeer entire turn", "Oversteer entire turn"
])
run_type = st.radio("Run Type", ["Qualifying", "Short Run", "Long Run"])
current_temp = st.slider("Track Temperature (°F)", 60, 140, 90)

# === Track-Corner Setup Feedback ===
st.markdown("## 📍 Feedback-Based Tuning Suggestions")
try:
    baseline_temp = corner_rules[track][corner].get("baseline_temp", 85)
    temp_diff = current_temp - baseline_temp
    if abs(temp_diff) > 10:
        st.warning(f"Track is {abs(temp_diff)}°F {'hotter' if temp_diff > 0 else 'cooler'} than baseline.")

    tips = corner_rules[track][corner]["rules"].get(feedback, [])
    if tips:
        for tip in tips:
            st.write(f"➤ {tip}")
    else:
        st.info("No specific rules for this condition yet. Use fallback tuning advice:")
        st.write("- Soften shock rebound to stabilize body control")
        st.write("- Adjust rear spring split for corner exit behavior")

except:
    st.warning("Error loading feedback logic.")

# === Input Method ===
mode = st.radio("Choose Input Method", ["Upload Setup File", "Enter Setup Manually"])
setup_data = {}

# === Manual Entry Mode ===
if mode == "Enter Setup Manually":
    # ➤ TIRES
    st.markdown("## 🛞 Tires")
    for corner in ["LF", "RF", "LR", "RR"]:
        setup_data[f"{corner}_Pressure"] = st.slider(f"{corner} Cold Pressure (psi)", 10.0, 30.0, 20.0, 0.5)

    # ➤ CHASSIS
    st.markdown("## 🛑 Chassis & Brakes")
    setup_data["Nose_Weight"] = st.slider("Nose Weight (%)", 49.0, 52.0, 51.0)
    setup_data["Crossweight"] = st.slider("Crossweight (%)", 48.0, 52.0, 50.0)
    setup_data["Front_Bias"] = st.slider("Front Brake Bias (%)", 30.0, 60.0, 38.0)
    setup_data["Front_MC"] = st.selectbox("Front Master Cylinder", ["0.625\"", "0.7\"", "0.75\"", "0.875\"", "0.9\"", "1.0\""])
    setup_data["Rear_MC"] = st.selectbox("Rear Master Cylinder", ["0.625\"", "0.7\"", "0.75\"", "0.875\"", "0.9\"", "1.0\""])
    setup_data["Steering_Pinion"] = st.selectbox("Steering Pinion (mm/rev)", ["40", "50", "60"])
    setup_data["Steering_Offset"] = st.slider("Steering Offset (deg)", -5.0, 5.0, 3.0, 0.1)

    # ➤ SUSPENSION
    st.markdown("## 🔧 Suspension")
    for corner in ["LF", "RF", "LR", "RR"]:
        st.markdown(f"### {corner}")
        setup_data[f"{corner}_Spring"] = st.slider(f"{corner} Spring Rate", 200, 3200, 1500)
        setup_data[f"{corner}_Offset"] = st.slider(f"{corner} Shock Collar Offset (in)", 3.0, 5.0, 4.0, 0.1)
        setup_data[f"{corner}_Camber"] = st.slider(f"{corner} Camber (°)", -6.0, +6.0, 0.0)
        if "F" in corner:
            setup_data[f"{corner}_Caster"] = st.slider(f"{corner} Caster (°)", 8.0, 18.0, 12.0)
        setup_data[f"{corner}_Toe"] = st.slider(f"{corner} Toe (in)", -0.25, 0.25, 0.0)
        for adj in ["LS_Comp", "HS_Comp", "HS_Comp_Slope", "LS_Rebound", "HS_Rebound", "HS_Rebound_Slope"]:
            setup_data[f"{corner}_{adj}"] = st.slider(f"{corner} {adj.replace('_', ' ')}", 0, 10, 5)

    # ➤ DRIVELINE
    st.markdown("## 🔩 Rear End & Driveline")
    setup_data["Final_Drive"] = st.selectbox("Final Drive Ratio", ["4.050", "4.075", "4.100", "4.125", "4.150"])
    setup_data["Diff_Preload"] = st.slider("Differential Preload (ft-lbs)", 0, 75, 25)
    setup_data["RearARB_Diameter"] = st.selectbox("Rear ARB Diameter", ["1.4\"", "1.5\"", "1.6\""])
    setup_data["RearARB_Arm"] = st.selectbox("Rear ARB Arm", ["P1", "P2", "P3", "P4", "P5"])
    setup_data["RearARB_Preload"] = st.slider("Rear ARB Preload (ft-lbs)", -200.0, 0.0, 0.0)
    setup_data["RearARB_Attach"] = st.selectbox("Rear ARB Attach", ["1", "2"])

# === Setup Upload Placeholder ===
if mode == "Upload Setup File":
    st.file_uploader("Upload iRacing .html setup", type=["html"])
    st.info("Setup parsing coming soon!")

# === Placeholder Tuning Output ===
st.markdown("## 🧠 Recommended Adjustments")
if mode == "Enter Setup Manually":
    if setup_data["Crossweight"] > 51.5:
        st.write("- Lower crossweight for better rotation.")
    if setup_data["RR_Pressure"] > 28.0:
        st.write("- Reduce RR pressure to improve rear grip on exit.")
    if run_type == "Long Run" and setup_data["Nose_Weight"] > 51.2:
        st.write("- Lower nose weight to reduce front tire wear over long runs.")

# === Future IBT Analysis ===
st.markdown("## 📊 Telemetry Analysis (Coming Soon)")
st.file_uploader("Upload .ibt telemetry file", type=["ibt"])
st.caption("Once supported, shock velocity, ride height, and G-forces will appear here for tuning help.")

st.markdown("---")
st.caption("ShearerPNW Easy Tuner – Full Manual Input Mode + Track Feedback v1.2")
