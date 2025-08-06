import streamlit as st
import json
import os

# Access control
if st.text_input("Enter Access Code") != "tune2025":
    st.stop()

st.title("ShearerPNW Easy Tuner")
st.subheader("NASCAR + GT3 Setup Assistant")

car = st.selectbox("Select Car", [
    "ARCA Menards", "NASCAR Next Gen", "NASCAR Trucks", "NASCAR Xfinity", "Ford Mustang GT3"
])

track = st.selectbox("Select Track", [
    "Atlanta Motor Speedway", "Auto Club Speedway", "Bristol Motor Speedway", "Bristol Motor Speedway - Dirt",
    "Canadian Tire Motorsport Park", "Charlotte Motor Speedway", "Charlotte Roval", "Chicagoland Speedway",
    "Circuit of the Americas", "Darlington Raceway", "Daytona International Speedway", "Daytona Road Course",
    "Dover Motor Speedway", "Eldora Speedway", "Gateway (WWT Raceway)", "Homestead-Miami Speedway",
    "Indianapolis Motor Speedway", "Indianapolis Road Course", "Iowa Speedway", "Kansas Speedway",
    "Kentucky Speedway", "Las Vegas Motor Speedway", "Los Angeles Memorial Coliseum", "Lucas Oil Raceway (IRP)",
    "Martinsville Speedway", "Michigan International Speedway", "Milwaukee Mile", "Nashville Fairgrounds Speedway",
    "Nashville Superspeedway", "New Hampshire Motor Speedway", "North Wilkesboro Speedway", "Phoenix Raceway",
    "Pocono Raceway", "Portland International Raceway", "Richmond Raceway", "Road America", "Rockingham Speedway",
    "Sonoma Raceway", "South Boston Speedway", "Talladega Superspeedway", "Texas Motor Speedway",
    "Watkins Glen International", "World Wide Technology Raceway"
])

run_type = st.radio("Run Type", ["Qualifying", "Short Run", "Long Run"])

st.markdown("### Handling Feedback")
entry = st.slider("Corner Entry", -5, 5, 0)
mid = st.slider("Mid Corner", -5, 5, 0)
exit = st.slider("Corner Exit", -5, 5, 0)

uploaded_file = st.file_uploader("Upload your iRacing setup (.html)", type=["html"])
if uploaded_file:
    st.success("Setup file uploaded.")

st.markdown("### Recommended Adjustments")
if entry < 0:
    st.write("- Lower brake bias by 1–2% (car is loose on entry)")
elif entry > 0:
    st.write("- Raise brake bias by 1–2% (car is tight on entry)")

if mid < 0:
    st.write("- Soften front ARB or increase RF rebound (mid corner is loose)")
elif mid > 0:
    st.write("- Stiffen front ARB or reduce front rebound (mid corner is tight)")

if exit < 0:
    st.write("- Soften RR spring or reduce RR rebound (loose on exit)")
elif exit > 0:
    st.write("- Add RR spring preload or increase rebound (tight on exit)")

st.write("- Adjust crossweight ±0.2% based on balance")
st.write("- Tire pressure ±0.5 psi (respect iRacing limits)")
st.write("- Monitor ride height effect on RF/RR platform")

st.markdown("### Editables (Car Profiles Preview)")
if os.path.exists("ShearerPNW_Easy_Tuner_Editables/car_profiles.json"):
    with open("ShearerPNW_Easy_Tuner_Editables/car_profiles.json") as f:
        data = json.load(f)
    st.json(data)
