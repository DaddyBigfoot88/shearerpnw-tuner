import streamlit as st

st.set_page_config(page_title="ShearerPNW Easy Tuner", layout="wide")

# (Optional) simple access control
# if st.text_input("Enter Access Code") != "Shearer":
#     st.stop()

# --- Centered landing layout ---
left, mid, right = st.columns([1, 2, 1])
with mid:
    st.title("ShearerPNW Easy Tuner")
    st.subheader("Pick what you want to do")

    st.markdown("### Quick Links")
    nav_ok = False
    try:
        # Streamlit 1.26+ supports page_link
        st.page_link("pages/1_Telemetry_Viewer.py", label="🤖 AI Setup Prep (Telemetry)")
        st.page_link("pages/2_Setup_Coach.py", label="🧠 Setup Coach (Question Mode)")
        nav_ok = True
    except Exception:
        nav_ok = False

    if not nav_ok:
        st.caption("Your Streamlit version looks older. Use the buttons below.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🤖 AI Setup Prep (Telemetry)"):
                try:
                    st.switch_page("pages/1_Telemetry_Viewer.py")
                except Exception:
                    st.warning("Update Streamlit to enable native page links.")
        with c2:
            if st.button("🧠 Setup Coach (Question Mode)"):
                try:
                    st.switch_page("pages/2_Setup_Coach.py")
                except Exception:
                    st.warning("Update Streamlit to enable native page links.")

    st.markdown("---")
    st.markdown("#### Heads up")
    st.write("- **AI Setup Prep (Telemetry):** Prep your run data and export a clean package for AI coaching. No auto-downloads.")
    st.write("- **Setup Coach (Question Mode):** Answer corner-by-corner questions and get setup changes right in the app.")

st.markdown("---")
st.caption("ShearerPNW • Built in the PNW 🤘")

