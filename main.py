import streamlit as st
import json
import os

# 🔒 Access Control
if st.text_input("Enter Access Code") != "Shearer":
    st.stop()

st.title("ShearerPNW Easy Tuner")
st.subheader("NASCAR Next Gen Manual Setup Input")

# 🧠 Load Track-Corner Rules
corner_rules_path = "ShearerPNW_Easy_Tuner_Editables/track_corner_rules.json"
corner_rules = {}
if os.path.exists(corner_rules_path):
    with open(corner_rules_path) as f:
        corner_rules = json.load(f)

# 🚗 Car is fixed to Next Gen
car = "NASCAR Next Gen"

# 🏁 Track and Run Type
track = st.selectbox("Select Track", [
    "Atlanta Motor Speedway", "Auto Club Speedway", "Bristol Motor Speedway",
    "Charlotte Motor Speedway", "Charlotte Roval", "Darlington Raceway",
    "Daytona International Speedway", "Dover Motor Speedway", "Gateway (WWT Raceway)",
    "Homestead-Miami Speedway", "Iowa Speedway", "Kansas Speedway",
    "Las Vegas Motor Speedway", "Martinsville Speedway", "Michigan International Speedway",
    "New Hampshire Motor Speedway", "North Wilkesboro Speedway", "Phoenix Raceway",
    "Pocono Raceway", "Richmond Raceway", "Rockingham Speedway", "Sonoma Raceway",
    "South Boston Speedway", "Talladega Superspeedway", "Texas Motor Speedway",
    "Watkins Glen International"
])
run_type = st.radio("Run Type", ["Qualifying", "Short Run", "Long Run"])

# 📍 Track Map Feedback Input
corner = st.selectbox("Select Track Corner", ["T1", "T2", "T3", "T5", "T6", "T7"])
feedback = st.selectbox("How does the car feel?", [
    "Loose on entry", "Loose mid-corner", "Loose on exit",
    "Tight on entry", "Tight mid-corner", "Tight on exit"
])

# 🛠 Manual Setup Input or Upload
mode = st.radio("Choose Input Method", ["Upload Setup File", "Enter Setup Manually"])
setup_data = {}

if mode == "Enter Setup Manually":
    st.markdown("## 🛞 Tires")
    col1, col2 = st.columns(2)
    with col1:
        setup_data["LF_Pressure"] = st.slider("LF Cold Pressure (psi)", 10.0, 30.0, 13.0, 0.5)
        setup_data["LR_Pressure"] = st.slider("LR Cold Pressure (psi)", 10.0, 30.0, 13.0, 0.5)
    with col2:
        setup_data["RF_Pressure"] = st.slider("RF Cold Pressure (psi)", 10.0, 30.0, 27.0, 0.5)
        setup_data["RR_Pressure"] = st.slider("RR Cold Pressure (psi)", 10.0, 30.0, 27.0, 0.5)

    st.markdown("## 🛑 Chassis & Brakes")
    setup_data["Nose_Weight"] = st.slider("Nose Weight (%)", 49.0, 52.0, 51.0)
    setup_data["Front_Bias"] = st.slider("Front Brake Bias (%)", 30.0, 60.0, 38.0)
    setup_data["Front_MC"] = st.selectbox("Front MC Size", ["0.625\"", "0.7\"", "0.75\"", "0.875\"", "0.9\"", "1.0\""])
    setup_data["Rear_MC"] = st.selectbox("Rear MC Size", ["0.625\"", "0.7\"", "0.75\"", "0.875\"", "0.9\"", "1.0\""])
    setup_data["Steering_Pinion"] = st.selectbox("Steering Pinion (mm/rev)", ["40", "50", "60"])
    setup_data["Steering_Offset"] = st.slider("Steering Offset (deg)", -5.0, 5.0, 3.0, 0.1)

    st.markdown("## 🔧 Suspension (Per Corner)")
    for corner_name in ["LF", "RF", "LR", "RR"]:
        st.markdown(f"### {corner_name}")
        setup_data[f"{corner_name}_Spring"] = st.slider(f"{corner_name} Spring Rate (lb/in)", 200, 3200, 1500)
        setup_data[f"{corner_name}_Shock_Offset"] = st.slider(f"{corner_name} Shock Collar Offset (in)", 3.0, 5.0, 4.0, 0.1)
        setup_data[f"{corner_name}_Camber"] = st.slider(f"{corner_name} Camber (°)", -6.0, +6.0, 0.0, 0.1)
        if "F" in corner_name:
            setup_data[f"{corner_name}_Caster"] = st.slider(f"{corner_name} Caster (°)", +8.0, +18.0, +10.0, 0.1)
        setup_data[f"{corner_name}_Toe"] = st.slider(f"{corner_name} Toe (in)", -0.25, 0.25, 0.0, 0.01)
        setup_data[f"{corner_name}_LS_Comp"] = st.slider(f"{corner_name} LS Compression", 0, 10, 5)
        setup_data[f"{corner_name}_HS_Comp"] = st.slider(f"{corner_name} HS Compression", 0, 10, 5)
        setup_data[f"{corner_name}_HS_Comp_Slope"] = st.slider(f"{corner_name} HS Comp Slope", 0, 10, 5)
        setup_data[f"{corner_name}_LS_Rebound"] = st.slider(f"{corner_name} LS Rebound", 0, 10, 5)
        setup_data[f"{corner_name}_HS_Rebound"] = st.slider(f"{corner_name} HS Rebound", 0, 10, 5)
        setup_data[f"{corner_name}_HS_Rebound_Slope"] = st.slider(f"{corner_name} HS Rebound Slope", 0, 10, 5)

    st.markdown("## 🔩 Rear End & Driveline")
    setup_data["Final_Drive"] = st.selectbox("Final Drive Ratio", ["4.050", "4.075", "4.100", "4.125", "4.150"])
    setup_data["Diff_Preload"] = st.slider("Differential Preload (ft-lbs)", 0, 75, 0)
    setup_data["RearARB_Diameter"] = st.selectbox("Rear ARB Diameter", ["1.4\"", "1.5\"", "1.6\""])
    setup_data["RearARB_Arm"] = st.selectbox("Rear ARB Arm", ["P1", "P2", "P3", "P4", "P5"])
    setup_data["RearARB_Preload"] = st.slider("Rear ARB Preload (ft-lbs)", -200.0, 0.0, 0.0, 1.0)
    setup_data["RearARB_Attach"] = st.selectbox("Rear ARB Attach", ["1", "2"])

# 📂 Upload File (Future Parsing)
if mode == "Upload Setup File":
    uploaded_file = st.file_uploader("Upload your iRacing setup (.html)", type=["html"])
    if uploaded_file:
        st.success("Setup file uploaded.")
        st.warning("Setup parsing coming in future update.")

# 🧠 Recommended Adjustments (simple logic for now)
st.markdown("## 🧠 Recommended Adjustments")
if mode == "Enter Setup Manually":
    if setup_data.get("RR_Pressure", 27.0) > 28.0:
        st.write("- Lower RR pressure for more exit grip.")
    if run_type == "Long Run" and setup_data.get("Nose_Weight", 51.0) > 51.5:
        st.write("- Reduce nose weight to delay front wear in long runs.")
    if setup_data.get("RF_Spring", 300) > setup_data.get("LF_Spring", 300) + 500:
        st.write("- Front spring split may cause splitter stall or nose dive.")

# 📍 Track-Corner Feedback Rules
st.markdown("## 📍 Track-Corner Feedback Suggestions")
try:
    tips = corner_rules.get(track, {}).get(corner, {}).get("rules", {}).get(feedback, [])
    if tips:
        for tip in tips:
            st.write(f"➤ {tip}")
    else:
        st.info("No tips available for this feedback at that corner.")
except:
    st.warning("Error loading corner-based tips.")

# 📄 Optional: Show JSON Preview
st.markdown("### 📁 Car Profile Preview")
editable_path = "ShearerPNW_Easy_Tuner_Editables/car_profiles.json"
if os.path.exists(editable_path):
    with open(editable_path) as f:
        try:
            st.json(json.load(f))
        except:
            st.warning("Could not parse JSON file.")
else:
    st.info("No car_profiles.json found.")

st.markdown("---")
st.caption("ShearerPNW Easy Tuner – v1.1 (Manual Entry + Corner Feedback)")
