# Setup Coach – question-based setup helper (no ChatGPT) + TEMP COMPENSATION
import json, pathlib, re
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(layout="wide")
st.title("Setup Coach (Question Mode)")
st.caption("Answer a few questions. I’ll suggest setup changes using your rules file. No ChatGPT needed.")

TRACKS_JSON_PATH = pathlib.Path("ShearerPNW_Easy_Tuner_Editables/tracks.json")
RULES_PATH = pathlib.Path("ShearerPNW_Easy_Tuner_Editables/setup_rules_nextgen.json")
CORNER_RULES_PATH = pathlib.Path("ShearerPNW_Easy_Tuner_Editables/track_corner_rules.json")  # for optional baseline_temp per track

def load_json_or(path: pathlib.Path, default: dict):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:
        st.error(f"Error reading {path}: {e}")
    return default

tracks = load_json_or(TRACKS_JSON_PATH, {})
setup_rules = load_json_or(RULES_PATH, {
    "allowed_parameters": {
        "tires": ["LF_pressure","RF_pressure","LR_pressure","RR_pressure"],
        "suspension": [
            "LF_shock_rebound_clicks","RF_shock_rebound_clicks","LR_shock_rebound_clicks","RR_shock_rebound_clicks",
            "LF_shock_bump_clicks","RF_shock_bump_clicks","LR_shock_bump_clicks","RR_shock_bump_clicks",
            "front_swaybar_stiffness","rear_swaybar_stiffness","front_spring_rate","rear_spring_rate"
        ],
        "chassis": ["crossweight_percent","front_ride_height_in","rear_ride_height_in","rear_trackbar_in"],
        "rear_end": ["diff_preload_ftlbs","gear_note"]
    },
    "limits": {
        "pressure": {"min_psig": 10.0, "max_psig": 60.0, "increments_psig": 0.5},
        "shock_clicks": {"min_clicks": 0, "max_clicks": 10, "increments": 1},
        "spring_rate": {"min_lbin": 100, "max_lbin": 2200, "increments": 25},
        "ride_height": {"min_in": 2.0, "max_in": 6.0, "increments": 0.05},
        "crossweight": {"min_pct": 45.0, "max_pct": 55.0, "increments": 0.1},
        "trackbar": {"min_in": 5.0, "max_in": 12.0, "increments": 0.25},
        "diff_preload": {"min_ftlbs": 0, "max_ftlbs": 75, "increments": 5}
    },
    "version": "fallback-1.0"
})
corner_rules = load_json_or(CORNER_RULES_PATH, {})  # may hold baseline_temp per track

def sev_bucket(n): 
    return "slight" if n <=3 else ("moderate" if n <=7 else "severe")

def mk_delta(name, delta, units):
    sign = "+" if delta > 0 else ""
    return f"{name}: {sign}{delta:g}{units}"

ALLOWED = setup_rules.get("allowed_parameters", {})
LIM = setup_rules.get("limits", {})

# ----- SIDEBAR: track + run type -----
with st.sidebar:
    track_names = sorted(list(tracks.keys())) if tracks else ["Unknown Track"]
    idx = track_names.index("Watkins Glen International (Cup)") if "Watkins Glen International (Cup)" in track_names else 0
    track_pick = st.selectbox("Track", track_names, index=idx)
    corner_labels = tracks.get(track_pick, {}).get("corners", ["T1","T2","T3"])
    run_type = st.radio("Run type", ["Practice","Qualifying","Race"], index=0, horizontal=True)

# ----- CORNER FEEL INPUTS -----
st.header("Corner Feel")
DEFAULT_FEELINGS = [
    "No issue / skip",
    "Loose on entry","Loose mid-corner","Loose on exit",
    "Tight on entry","Tight mid-corner","Tight on exit",
    "Brakes locking","Traction wheelspin","Porpoising / Bottoming","Other"
]

if "coach_feedback" not in st.session_state or st.session_state.get("_coach_track") != track_pick:
    st.session_state.coach_feedback = {c: {"feels":"No issue / skip","severity":0,"note":""} for c in corner_labels}
    st.session_state._coach_track = track_pick

cols = st.columns(3)
for i, c in enumerate(corner_labels):
    with cols[i % 3]:
        st.markdown(f"**{c}**")
        feels = st.selectbox(f"{c} feel", DEFAULT_FEELINGS, index=0, key=f"coach_feel_{re.sub(r'[^a-z0-9]+','_',c.lower())}")
        severity = st.slider(f"{c} severity", 0, 10, st.session_state.coach_feedback[c].get("severity",0), key=f"coach_sev_{re.sub(r'[^a-z0-9]+','_',c.lower())}")
        note = st.text_input(f"{c} note", value=st.session_state.coach_feedback[c].get("note",""), key=f"coach_note_{re.sub(r'[^a-z0-9]+','_',c.lower())}")
        st.session_state.coach_feedback[c] = {"feels": feels, "severity": int(severity), "note": note}

st.markdown("---")
st.caption("Severity: 1–3 slight · 4–7 moderate · 8–10 severe")

# ======== TEMP COMPENSATION (middle of page) ========
st.header("Track Temperature Compensation")
# Try to read a per-track baseline from corner_rules if present
default_baseline = 85
try:
    default_baseline = corner_rules.get(track_pick, {}).get("baseline_temp", 85)
except Exception:
    pass

c1, c2 = st.columns(2)
with c1:
    baseline_temp = st.number_input("Baseline Setup Temperature (°F)", 40, 150, int(default_baseline))
with c2:
    current_temp = st.number_input("Current Track Temperature (°F)", 40, 150, int(default_baseline))

def temp_scale_from_diff(diff):
    ad = abs(diff)
    if ad <= 5: return 0  # no change
    if ad <= 10: return 1
    if ad <= 20: return 2
    return 3

def suggest_for_temp(baseline, current):
    """Return temp-only suggestion deltas grouped by category, using allowed+limits."""
    out = {"tires": [], "chassis": [], "suspension": [], "rear_end": []}
    diff = current - baseline
    scale = temp_scale_from_diff(diff)
    if scale == 0:
        return out, diff, scale

    psi_step = LIM.get("pressure", {}).get("increments_psig", 0.5)
    shock_step = LIM.get("shock_clicks", {}).get("increments", 1)
    spring_step = LIM.get("spring_rate", {}).get("increments", 25)
    diff_step = LIM.get("diff_preload", {}).get("increments", 5)
    ride_step = LIM.get("ride_height", {}).get("increments", 0.05)

    hotter = diff > 0  # hotter than baseline => usually less grip

    # Tires: adjust all four if allowed
    for tname in ("LF_pressure","RF_pressure","LR_pressure","RR_pressure"):
        if tname in ALLOWED.get("tires", []):
            delta = -psi_step*scale if hotter else +psi_step*scale
            out["tires"].append(mk_delta(tname, delta, " psi"))

    # Shocks: stiffer when hotter (add bump clicks), softer when cooler (remove bump clicks)
    shock_bump_names = ("LF_shock_bump_clicks","RF_shock_bump_clicks","LR_shock_bump_clicks","RR_shock_bump_clicks")
    for sname in shock_bump_names:
        if sname in ALLOWED.get("suspension", []):
            delta = +shock_step*scale if hotter else -shock_step*scale
            out["suspension"].append(mk_delta(sname, delta, " clicks"))

    # Springs / Preload tweaks
    if hotter:
        if "rear_spring_rate" in ALLOWED.get("suspension", []):
            out["suspension"].append(mk_delta("rear_spring_rate", +spring_step*scale, " lb/in"))
        if "diff_preload_ftlbs" in ALLOWED.get("rear_end", []):
            out["rear_end"].append(mk_delta("diff_preload_ftlbs", +diff_step*scale, " ft-lbs"))
    else:
        if "diff_preload_ftlbs" in ALLOWED.get("rear_end", []):
            out["rear_end"].append(mk_delta("diff_preload_ftlbs", -diff_step*scale, " ft-lbs"))
        # A little rake for cooler track if allowed (raise rear a touch)
        if "rear_ride_height_in" in ALLOWED.get("chassis", []):
            out["chassis"].append(mk_delta("rear_ride_height_in", +ride_step*scale, " in"))

    return out, diff, scale

# ----- RULE ENGINE: corner symptoms -----
def suggest_for_symptom(feel: str, sev: str):
    out = {"tires": [], "chassis": [], "suspension": [], "rear_end": []}
    scale = {"slight":1, "moderate":2, "severe":3}[sev]

    psi_step = LIM.get("pressure", {}).get("increments_psig", 0.5)
    trackbar_step = LIM.get("trackbar", {}).get("increments", 0.25)
    xwt_step = LIM.get("crossweight", {}).get("increments", 0.1)
    shock_step = LIM.get("shock_clicks", {}).get("increments", 1)
    spring_step = LIM.get("spring_rate", {}).get("increments", 25)
    diff_step = LIM.get("diff_preload", {}).get("increments", 5)

    f = feel.lower()

    # --- LOOSE ---
    if "loose on entry" in f:
        if "LF_pressure" in ALLOWED.get("tires", []): out["tires"].append(mk_delta("LF_pressure", -psi_step*scale, " psi"))
        if "RR_pressure" in ALLOWED.get("tires", []): out["tires"].append(mk_delta("RR_pressure", -psi_step*scale, " psi"))
        if "rear_trackbar_in" in ALLOWED.get("chassis", []): out["chassis"].append(mk_delta("rear_trackbar_in", -trackbar_step*scale, " in"))
        if "crossweight_percent" in ALLOWED.get("chassis", []): out["chassis"].append(mk_delta("crossweight_percent", +xwt_step*scale, " %"))
        if "LF_shock_rebound_clicks" in ALLOWED.get("suspension", []): out["suspension"].append(mk_delta("LF_shock_rebound_clicks", +shock_step*scale, " clicks"))
    if "loose mid-corner" in f:
        if "rear_swaybar_stiffness" in ALLOWED.get("suspension", []): out["suspension"].append(mk_delta("rear_swaybar_stiffness", -1*scale, " step"))
        if "front_swaybar_stiffness" in ALLOWED.get("suspension", []): out["suspension"].append(mk_delta("front_swaybar_stiffness", +1*scale, " step"))
        if "rear_spring_rate" in ALLOWED.get("suspension", []): out["suspension"].append(mk_delta("rear_spring_rate", -spring_step*scale, " lb/in"))
        if "RR_pressure" in ALLOWED.get("tires", []): out["tires"].append(mk_delta("RR_pressure", -psi_step*scale, " psi"))
    if "loose on exit" in f:
        if "diff_preload_ftlbs" in ALLOWED.get("rear_end", []): out["rear_end"].append(mk_delta("diff_preload_ftlbs", +diff_step*scale, " ft-lbs"))
        if "rear_trackbar_in" in ALLOWED.get("chassis", []): out["chassis"].append(mk_delta("rear_trackbar_in", -trackbar_step*scale, " in"))
        if "RR_pressure" in ALLOWED.get("tires", []): out["tires"].append(mk_delta("RR_pressure", -psi_step*scale, " psi"))
        if "RR_shock_rebound_clicks" in ALLOWED.get("suspension", []): out["suspension"].append(mk_delta("RR_shock_rebound_clicks", -shock_step*scale, " clicks"))

    # --- TIGHT ---
    if "tight on entry" in f:
        if "crossweight_percent" in ALLOWED.get("chassis", []): out["chassis"].append(mk_delta("crossweight_percent", -xwt_step*scale, " %"))
        if "rear_trackbar_in" in ALLOWED.get("chassis", []): out["chassis"].append(mk_delta("rear_trackbar_in", +trackbar_step*scale, " in"))
        if "RF_pressure" in ALLOWED.get("tires", []): out["tires"].append(mk_delta("RF_pressure", -psi_step*scale, " psi"))
    if "tight mid-corner" in f:
        if "front_swaybar_stiffness" in ALLOWED.get("suspension", []): out["suspension"].append(mk_delta("front_swaybar_stiffness", -1*scale, " step"))
        if "rear_swaybar_stiffness" in ALLOWED.get("suspension", []): out["suspension"].append(mk_delta("rear_swaybar_stiffness", +1*scale, " step"))
        if "front_spring_rate" in ALLOWED.get("suspension", []): out["suspension"].append(mk_delta("front_spring_rate", -spring_step*scale, " lb/in"))
        if "LF_pressure" in ALLOWED.get("tires", []): out["tires"].append(mk_delta("LF_pressure", -psi_step*scale, " psi"))
    if "tight on exit" in f:
        if "diff_preload_ftlbs" in ALLOWED.get("rear_end", []): out["rear_end"].append(mk_delta("diff_preload_ftlbs", -diff_step*scale, " ft-lbs"))
        if "rear_trackbar_in" in ALLOWED.get("chassis", []): out["chassis"].append(mk_delta("rear_trackbar_in", +trackbar_step*scale, " in"))
        if "RR_pressure" in ALLOWED.get("tires", []): out["tires"].append(mk_delta("RR_pressure", +psi_step*scale, " psi"))

    # --- Other symptoms ---
    if "brakes locking" in f:
        if "LF_shock_rebound_clicks" in ALLOWED.get("suspension", []): out["suspension"].append(mk_delta("LF_shock_rebound_clicks", -shock_step*scale, " clicks"))
        if "RF_pressure" in ALLOWED.get("tires", []): out["tires"].append(mk_delta("RF_pressure", -psi_step*scale, " psi"))
    if "traction wheelspin" in f:
        if "RR_shock_rebound_clicks" in ALLOWED.get("suspension", []): out["suspension"].append(mk_delta("RR_shock_rebound_clicks", -shock_step*scale, " clicks"))
        if "diff_preload_ftlbs" in ALLOWED.get("rear_end", []): out["rear_end"].append(mk_delta("diff_preload_ftlbs", +diff_step*scale, " ft-lbs"))
        if "RR_pressure" in ALLOWED.get("tires", []): out["tires"].append(mk_delta("RR_pressure", -psi_step*scale, " psi"))
    if "porpoising" in f or "bottoming" in f:
        if "front_spring_rate" in ALLOWED.get("suspension", []): out["suspension"].append(mk_delta("front_spring_rate", +spring_step*scale, " lb/in"))
        if "rear_spring_rate" in ALLOWED.get("suspension", []): out["suspension"].append(mk_delta("rear_spring_rate", +spring_step*scale, " lb/in"))
        if "front_ride_height_in" in ALLOWED.get("chassis", []): out["chassis"].append(mk_delta("front_ride_height_in", +LIM.get("ride_height",{}).get("increments",0.05)*scale, " in"))

    return out

# ----- COMPUTE -----
btn = st.button("Compute Suggestions")
if btn:
    per_corner = []
    agg = {"tires": [], "chassis": [], "suspension": [], "rear_end": []}

    # 1) Temp compensation first
    temp_out, temp_diff, temp_scale = suggest_for_temp(baseline_temp, current_temp)
    for k in agg:
        agg[k].extend(temp_out[k])

    # 2) Corner-based rules
    for corner, fb in st.session_state.coach_feedback.items():
        feel = fb["feels"]
        sev = sev_bucket(fb["severity"])
        if feel != "No issue / skip" and fb["severity"] > 0:
            s = suggest_for_symptom(feel, sev)
            per_corner.append({"corner": corner, "feel": feel, "severity": sev, "note": fb.get("note",""), "suggestions": s})
            for k in agg:
                agg[k].extend(s[k])

    # --- Output ---
    if temp_scale > 0:
        direction = "hotter" if temp_diff > 0 else "cooler"
        st.info(f"Temp compensation applied: track is {abs(temp_diff)}°F {direction} than baseline "
                f"(severity x{temp_scale}).")

    if not per_corner and temp_scale == 0:
        st.info("No problems selected and temp is near baseline. Nothing to change.")
    else:
        st.subheader("Key Findings")
        if temp_scale > 0:
            st.write(f"- **Temperature**: {abs(temp_diff)}°F {'hotter' if temp_diff>0 else 'cooler'} than baseline")
        for item in per_corner:
            st.write(f"- **{item['corner']}**: {item['feel']} ({item['severity']})" + (f" — {item['note']}" if item['note'] else ""))

        st.subheader("Setup Changes")
        def list_block(title, arr):
            if not arr: 
                return
            st.markdown(f"**{title}**")
            for line in arr:
                st.write(f"- {line}")

        list_block("Tires", agg["tires"])
        list_block("Chassis", agg["chassis"])
        list_block("Suspension", agg["suspension"])
        list_block("Rear End", agg["rear_end"])

        st.subheader("Why this helps")
        st.write("- **Temp compensation**: adjusts pressures/shocks so grip stays in the window.")
        st.write("- **Tires**: small pressure tweaks shift balance where you need it.")
        st.write("- **Crossweight/trackbar**: moves entry/exit balance without huge side effects.")
        st.write("- **Bars/springs/shocks**: tunes mid/exit behavior and compliance.")
        st.write("- **Diff preload**: more preload = tighter on exit; less = freer on exit.")

        st.subheader("Next Run Checklist")
        st.write("- Did the temp-compensated balance feel more consistent?")
        st.write("- Did the problem get better in that corner?")
        st.write("- Any new side effects?")
        st.write("- If still off, go one more step and re-test.")

        plan = {
            "track": track_pick,
            "run_type": run_type,
            "baseline_temp_f": baseline_temp,
            "current_temp_f": current_temp,
            "temp_diff_f": current_temp - baseline_temp,
            "inputs": st.session_state.coach_feedback,
            "recommendations": agg,
            "limits": LIM,
        }
        st.download_button("Download plan (.json)", data=json.dumps(plan, indent=2).encode("utf-8"),
                           file_name="setup_coach_plan.json", mime="application/json")
else:
    st.info("Pick corners, set how bad it is, set temps, then hit **Compute Suggestions**.")
