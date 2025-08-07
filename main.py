import streamlit as st
import json
import os

# Access control
if st.text_input("Enter Access Code") != "Shearer":
    st.stop()

st.title("ShearerPNW Easy Tuner")
st.subheader("NASCAR Next Gen Manual Setup Input")

# Car locked to Next Gen for now
car = "NASCAR Next Gen"

# Track selection
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

# Run type
run_type = st.radio("Run Type", ["Qualifying", "Short Run", "Long Run"])

# Input method
mode = st.radio("Choose Input Method", ["Upload Setup File", "Enter Setup Manually"])
setup_data = {}

if mode == "Enter Setup Manually":
    st.markdown("### 🛠 Suspension – Shock Clicks (0–10)")

    col1, col2 = st.columns(2)
    with col1:
        setup_data["LF_LS_Comp"] = st.slider("LF LS Compression", 0, 10, 5)
        setup_data["LF_LS_Rebound"] = st.slider("LF LS Rebound", 0, 10, 5)
        setup_data["LR_LS_Comp"] = st.slider("LR LS Compression", 0, 10, 5)
        setup_data["LR_LS_Rebound"] = st.slider("LR LS Rebound", 0, 10, 5)
    with col2:
        setup_data["RF_LS_Comp"] = st.slider("RF LS Compression", 0, 10, 5)
        setup_data["RF_LS_Rebound"] = st.slider("RF LS Rebound", 0, 10, 5)
        setup_data["RR_LS_Comp"] = st.slider("RR LS Compression", 0, 10, 5)
        setup_data["RR_LS_Rebound"] = st.slider("RR LS Rebound", 0, 10, 5)

    st.markdown("### 🌀 Springs & Ride Heights")

    setup_data["LF_Spring"] = st.slider("LF Spring Rate (lb/in)", 300, 800, 500)
    setup_data["RF_Spring"] = st.slider("RF Spring Rate (lb/in)", 300, 800, 500)
    setup_data["LR_Spring"] = st.slider("LR Spring Rate (lb/in)", 200, 600, 400)
    setup_data["RR_Spring"] = st.slider("RR Spring Rate (lb/in)", 200, 600, 400)

    setup_data["RF_RideHeight"] = st.slider("RF Ride Height (in)", 1.5, 3.0, 2.0, 0.01)
    setup_data["RR_RideHeight"] = st.slider("RR Ride Height (in)", 2.0, 3.5, 2.5, 0.01)

    st.markdown("### 🛑 Brakes, Balance & Driveline")
    setup_data["Brake_Bias"] = st.slider("Brake Bias (%)", 55.0, 70.0, 60.0)
    setup_data["Crossweight"] = st.slider("Crossweight (%)", 48.0, 52.0, 50.0)
    setup_data["Diff_Preload"] = st.slider("Differential Preload (ft-lbs)", 0, 75, 25)

# === Upload Mode Placeholder ===
if mode == "Upload Setup File":
    uploaded_file = st.file_uploader("Upload your iRacing setup (.html)", type=["html"])
    if uploaded_file:
        st.success("Setup file uploaded.")
        st.warning("Setup parsing coming in future update.")

# === Tuning Output ===
st.markdown("### 🧐 Recommended Adjustments")

if mode == "Enter Setup Manually":
    if setup_data["Brake_Bias"] > 67:
        st.write("- Lower brake bias 1–2% to improve corner entry rotation.")
    elif setup_data["Brake_Bias"] < 57:
        st.write("- Raise brake bias to prevent rear lock-up under braking.")

    if setup_data["RR_RideHeight"] > 2.9:
        st.write("- Reduce RR ride height slightly to stabilize exit.")
    elif setup_data["RR_RideHeight"] < 2.2:
        st.write("- Raise RR height if you feel tightness under throttle.")

    if setup_data["Crossweight"] > 51.5:
        st.write("- Lower crossweight 0.2–0.5% to help with corner entry.")
    elif setup_data["Crossweight"] < 49.0:
        st.write("- Raise crossweight slightly for throttle stability.")

    st.write("- Review front spring split for turn-in and platform control.")
    st.write("- Use shock clickers to fine-tune response in each corner.")

elif mode == "Upload Setup File":
    st.info("Manual tuning suggestions will appear here after file parsing is enabled.")

# === Corner Feedback Sliders ===
st.markdown("### 🔹 Track-Corner Based Feedback")
corner = st.selectbox("Select Track Corner", ["T1", "T2", "T3", "T5", "T6", "T7"])
feedback = st.selectbox("How does the car feel?", [
    "Loose on entry", "Loose mid-corner", "Loose on exit",
    "Tight on entry", "Tight mid-corner", "Tight on exit"
])

# === Load corner setup rules ===
corner_rules_path = "ShearerPNW_Easy_Tuner_Editables/track_corner_rules.json"
corner_rules = {}
if os.path.exists(corner_rules_path):
    with open(corner_rules_path) as f:
        corner_rules = json.load(f)

# === Show corner-based tips ===
st.markdown("### 📍 Corner-Based Suggestions")
try:
    tips = corner_rules.get(track, {}).get(corner, {}).get("rules", {}).get(feedback, [])
    if tips:
        for tip in tips:
            st.write(tip)
    else:
        st.info("No tips available for this feedback at that corner.")
except:
    st.warning("Error loading corner-based tips.")

# === Optional JSON Preview ===
st.markdown("### 🔍 Car Profile Data (JSON Preview)")
editable_path = "ShearerPNW_Easy_Tuner_Editables/car_profiles.json"
if os.path.exists(editable_path):
    with open(editable_path) as f:
        try:
            profile_data = json.load(f)
            st.json(profile_data)
        except:
            st.warning("Could not parse JSON from car_profiles.json")
else:
    st.info("No car profile file found at expected location.")

# === End of File ===
st.markdown("---")
st.caption("ShearerPNW Easy Tuner v1.1 – Now with Corner-Specific Feedback")
