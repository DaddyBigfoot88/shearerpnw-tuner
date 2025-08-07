import streamlit as st
import json
import os

# 🔒 Access Control
if st.text_input("Enter Access Code") != "Shearer":
    st.stop()

st.title("ShearerPNW Easy Tuner")
st.subheader("NASCAR Next Gen Feedback-Based Setup Assistant")

# 🧠 Load Track-Corner Rules
corner_rules_path = "ShearerPNW_Easy_Tuner_Editables/track_corner_rules.json"
corner_rules = {}
if os.path.exists(corner_rules_path):
    with open(corner_rules_path) as f:
        corner_rules = json.load(f)

# 🏁 Track Selection & Run Type
track = st.selectbox("Select Track", list(corner_rules.keys()))
run_type = st.radio("Run Type", ["Qualifying", "Short Run", "Long Run"])
corner = st.selectbox("Select Track Corner", list(corner_rules.get(track, {}).keys()))
feedback = st.selectbox("How does the car feel?", [
    "Loose on entry", "Loose mid-corner", "Loose on exit",
    "Tight on entry", "Tight mid-corner", "Tight on exit",
    "Bouncy mid-corner", "Hits bump and loses control",
    "Understeer entire turn", "Oversteer entire turn"
])

# 🌡️ Track & Baseline Temperature Comparison
current_temp = st.slider("Current Track Temperature (°F)", 60, 140, 90)
baseline_temp = corner_rules.get(track, {}).get(corner, {}).get("baseline_temp", 85)
st.slider("Baseline Setup Temperature (°F)", 60, 140, baseline_temp, disabled=True)

# 🧠 Feedback Suggestions
st.markdown("## 📍 Track-Corner Feedback Suggestions")
try:
    temp_diff = current_temp - baseline_temp

    if abs(temp_diff) > 10:
        if temp_diff > 0:
            st.warning(f"Track is {temp_diff}°F hotter than baseline – expect lower rear grip.")
        else:
            st.info(f"Track is {abs(temp_diff)}°F cooler – watch for early tire peak and increased front grip.")

    tips = corner_rules.get(track, {}).get(corner, {}).get("rules", {}).get(feedback, [])
    if tips:
        for tip in tips:
            st.write(f"➤ {tip}")
    else:
        st.info("No tips yet for this corner/feedback. Using general suggestions.")
        st.write("- Try adjusting rear rebound or preload.")
        st.write("- Review shock slopes or ride height differences.")
except:
    st.warning("Error loading rule logic or tips.")

# 📂 Setup File Upload (HTML) – Future Support
st.markdown("## 📄 Upload Setup File (Future Support)")
uploaded_file = st.file_uploader("Upload your iRacing setup (.html)", type=["html"])
if uploaded_file:
    st.success("Setup file uploaded. Parsing coming soon.")

# 📊 IBT Upload (Future Telemetry)
st.markdown("## 📊 Telemetry File Upload (.ibt)")
uploaded_ibt = st.file_uploader("Upload iRacing Telemetry (.ibt)", type=["ibt"])
if uploaded_ibt:
    st.success("IBT file uploaded. Visualization coming soon.")

# 🛠 Manual Setup (Moved to Bottom)
st.markdown("---")
st.markdown("## 🛠 Optional: Current Setup Entry (Does not affect logic yet)")
setup_data = {}

mode = st.radio("Setup Input Method", ["Enter Setup Manually", "Skip"])
if mode == "Enter Setup Manually":
    st.markdown("### 🛞 Tires")
    col1, col2 = st.columns(2)
    with col1:
        setup_data["LF_Pressure"] = st.slider("LF Cold Pressure (psi)", 10.0, 30.0, 13.0, 0.5)
        setup_data["LR_Pressure"] = st.slider("LR Cold Pressure (psi)", 10.0, 30.0, 13.0, 0.5)
    with col2:
        setup_data["RF_Pressure"] = st.slider("RF Cold Pressure (psi)", 10.0, 30.0, 27.0, 0.5)
        setup_data["RR_Pressure"] = st.slider("RR Cold Pressure (psi)", 10.0, 30.0, 27.0, 0.5)

    st.markdown("### 🛑 Chassis & Brakes")
    setup_data["Nose_Weight"] = st.slider("Nose Weight (%)", 49.0, 52.0, 51.0)
    setup_data["Front_Bias"] = st.slider("Front Brake Bias (%)", 30.0, 60.0, 38.0)
    setup_data["Front_MC"] = st.selectbox("Front MC Size", ["0.625\"", "0.7\"", "0.75\"", "0.875\"", "0.9\"", "1.0\""])
    setup_data["Rear_MC"] = st.selectbox("Rear MC Size", ["0.625\"", "0.7\"", "0.75\"", "0.875\"", "0.9\"", "1.0\""])

    st.markdown("### 🔧 Suspension (Per Corner)")
    for corner_name in ["LF", "RF", "LR", "RR"]:
        st.markdown(f"#### {corner_name}")
        setup_data[f"{corner_name}_Spring"] = st.slider(f"{corner_name} Spring Rate (lb/in)", 200, 3200, 1500)
        setup_data[f"{corner_name}_Shock_Offset"] = st.slider(f"{corner_name} Shock Collar Offset (in)", 3.0, 5.0, 4.0, 0.1)
        setup_data[f"{corner_name}_Camber"] = st.slider(f"{corner_name} Camber (°)", -6.0, +6.0, 0.0, 0.1)
        if "F" in corner_name:
            setup_data[f"{corner_name}_Caster"] = st.slider(f"{corner_name} Caster (°)", 8.0, 18.0, 10.0, 0.1)
        setup_data[f"{corner_name}_Toe"] = st.slider(f"{corner_name} Toe (in)", -0.25, 0.25, 0.0, 0.01)
        setup_data[f"{corner_name}_LS_Comp"] = st.slider(f"{corner_name} LS Compression", 0, 10, 5)
        setup_data[f"{corner_name}_HS_Comp"] = st.slider(f"{corner_name} HS Compression", 0, 10, 5)
        setup_data[f"{corner_name}_HS_Comp_Slope"] = st.slider(f"{corner_name} HS Comp Slope", 0, 10, 5)
        setup_data[f"{corner_name}_LS_Rebound"] = st.slider(f"{corner_name} LS Rebound", 0, 10, 5)
        setup_data[f"{corner_name}_HS_Rebound"] = st.slider(f"{corner_name} HS Rebound", 0, 10, 5)
        setup_data[f"{corner_name}_HS_Rebound_Slope"] = st.slider(f"{corner_name} HS Rebound Slope", 0, 10, 5)

    st.markdown("### 🔩 Rear End & Driveline")
    setup_data["Final_Drive"] = st.selectbox("Final Drive Ratio", ["4.050", "4.075", "4.100", "4.125", "4.150"])
    setup_data["Diff_Preload"] = st.slider("Differential Preload (ft-lbs)", 0, 75, 0)
    setup_data["RearARB_Diameter"] = st.selectbox("Rear ARB Diameter", ["1.4\"", "1.5\"", "1.6\""])
    setup_data["RearARB_Arm"] = st.selectbox("Rear ARB Arm", ["P1", "P2", "P3", "P4", "P5"])
    setup_data["RearARB_Preload"] = st.slider("Rear ARB Preload (ft-lbs)", -200.0, 0.0, 0.0, 1.0)
    setup_data["RearARB_Attach"] = st.selectbox("Rear ARB Attach", ["1", "2"])

# ✅ Done
st.markdown("---")
st.caption("ShearerPNW Easy Tuner – v1.1 | Feedback-Driven | Setup Input Optional")
