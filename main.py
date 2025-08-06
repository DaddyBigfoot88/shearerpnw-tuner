import streamlit as st
import json
import os

# Access control
if st.text_input("Enter Access Code") != "tune2025":
    st.stop()

st.title("ShearerPNW Easy Tuner")
st.subheader("NASCAR + GT3 Setup Assistant")

# Selectors
car = st.selectbox("Select Car", ["ARCA Menards", "NASCAR Next Gen", "NASCAR Trucks", "NASCAR Xfinity", "Ford Mustang GT3"])
track = st.text_input("Track Name")
run_type = st.radio("Run Type", ["Qualifying", "Short Run", "Long Run"])

# Sliders
st.markdown("### Handling Feedback")
entry = st.slider("Corner Entry", -5, 5, 0)
mid = st.slider("Mid Corner", -5, 5, 0)
exit = st.slider("Corner Exit", -5, 5, 0)

# File upload
uploaded_file = st.file_uploader("Upload your iRacing setup (.html)", type=["html"])
if uploaded_file:
    st.success("Setup file uploaded.")

# Output
st.markdown("### Recommended Adjustments")
st.write("- RF Rebound: +1 click")
st.write("- RR Ride Height: +0.05"")
st.write("- Crossweight: Adjust to 49.7%")

# Show Editables
st.markdown("### Editables (Car Profiles Preview)")
if os.path.exists("ShearerPNW_Easy_Tuner_Editables/car_profiles.json"):
    with open("ShearerPNW_Easy_Tuner_Editables/car_profiles.json") as f:
        data = json.load(f)
    st.json(data)
