# main.py — ShearerPNW Easy Tuner (Centered + Color + Big Buttons + Descriptions)
import streamlit as st

st.set_page_config(page_title="ShearerPNW Easy Tuner", page_icon="🏁", layout="wide")

# ===== CSS: center + responsive + color accents =====
st.markdown("""
<style>
  .appview-container .main .block-container{
    max-width: 900px;              /* comfy on desktop */
    margin-left: auto; margin-right: auto;
    padding-top: 0.5rem; padding-bottom: 2rem;
  }
  @media (max-width: 900px){
    .appview-container .main .block-container{
      max-width: 95vw; padding-left: 0.75rem; padding-right: 0.75rem;
    }
  }
  .hero {
    background: linear-gradient(135deg, #0ea5e9 0%, #22c55e 100%);
    color: white; border-radius: 16px;
    padding: 22px 20px; margin: 6px 0 18px;
    text-align: center;
    box-shadow: 0 8px 30px rgba(0,0,0,0.12);
  }
  .hero h1 { margin: 0; font-size: clamp(28px, 4.2vw, 40px); }
  .hero p  { margin: 6px 0 0; font-size: 15px; opacity: 0.95; }
  .section-title { text-align:center; font-size: 20px; margin: 14px 0 0; opacity: 0.9; }

  /* Big buttons */
  .bigbtn { 
    width: 100%; border: 2px solid #0ea5e9; border-radius: 14px;
    padding: 16px; font-size: 20px; font-weight: 600;
    background: #f8fafc; color: #0f172a;
    cursor: pointer; transition: all .15s ease;
  }
  .bigbtn:hover { background: #0ea5e9; color: white; }
  .card {
    border: 1px solid #e5e7eb; border-radius: 14px;
    padding: 14px; background: white; box-shadow: 0 6px 20px rgba(0,0,0,0.06);
  }
  .card h3{ margin: 0 0 6px; font-size: 18px; }
  .card p { margin: 0; font-size: 14px; color: #334155; }
  .center-note { text-align:center; color:#64748b; font-size: 13px; }
</style>
""", unsafe_allow_html=True)

# ===== HERO =====
st.markdown("""
<div class="hero">
  <h1>ShearerPNW Easy Tuner</h1>
  <p>Pick what you want to do. This app helps you dial in your iRacing NASCAR Next Gen setup — fast and simple.</p>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="section-title">Quick Links</div>', unsafe_allow_html=True)
st.write("")

# ===== BIG BUTTONS + DESCRIPTIONS =====
c1, c2 = st.columns(2, gap="large")

with c1:
    # Big button nav to Telemetry Viewer
    go_tv = st.button("🤖  AI Setup Prep (Telemetry)", key="go_tv", use_container_width=True)
    if go_tv:
        try:
            st.switch_page("pages/1_Telemetry_Viewer.py")
        except Exception:
            st.warning("If the button didn’t navigate, use the link below.")
    st.markdown("""
    <div class="card">
      <h3>What it does</h3>
      <p>Upload your iRacing telemetry (.csv or .ibt), pick the track, and add quick notes per corner. 
      Then export a clean bundle for ChatGPT with your track meta, rules, temps, and a quick stat pass. 
      It keeps things simple so AI can give tighter, track-aware feedback.</p>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/1_Telemetry_Viewer.py", label="Open AI Setup Prep (fallback link)")

with c2:
    # Big button nav to Setup Coach
    go_coach = st.button("🧠  Setup Coach (Question Mode)", key="go_coach", use_container_width=True)
    if go_coach:
        try:
            st.switch_page("pages/2_Setup_Coach.py")
        except Exception:
            st.warning("If the button didn’t navigate, use the link below.")
    st.markdown("""
    <div class="card">
      <h3>What it does</h3>
      <p>Tell the app how the car feels in each corner. We use rules, corner direction (left/right), banking, 
      and corner angle to scale changes. Run type (Practice/Qual/Race) adjusts how big the tweaks are. 
      You get a clear plan without sending anything to AI.</p>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/2_Setup_Coach.py", label="Open Setup Coach (fallback link)")

st.write("")
st.markdown('<div class="center-note">Pro tip: Start with Coach to get a baseline plan. Then use AI Setup Prep to double-check with telemetry context.</div>', unsafe_allow_html=True)
