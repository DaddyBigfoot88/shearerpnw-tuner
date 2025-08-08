
# Setup Coach – question-based helper with auto Left/Right + Banking/Angle scaling
# Uses corner metadata from tracks.json to mirror LF/RF for right-handers and
# scales deltas based on banking (deg) and corner angle (deg).

import json, pathlib, re
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(layout="wide")
st.title("Setup Coach (Question Mode)")
st.caption("Left/Right is auto from tracks.json. Deltas scale with banking & corner angle.")

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
setup_rules = load_json_or(RULES_PATH, {})
corner_rules = load_json_or(CORNER_RULES_PATH, {})  # may hold baseline_temp per track

# limits & allowed fallbacks
ALLOWED = setup_rules.get("allowed_parameters", {
    "tires": ["LF_pressure","RF_pressure","LR_pressure","RR_pressure"],
    "suspension": [
        "LF_shock_rebound_clicks","RF_shock_rebound_clicks","LR_shock_rebound_clicks","RR_shock_rebound_clicks",
        "LF_shock_bump_clicks","RF_shock_bump_clicks","LR_shock_bump_clicks","RR_shock_bump_clicks",
        "front_swaybar_stiffness","rear_swaybar_stiffness","front_spring_rate","rear_spring_rate"
    ],
    "chassis": ["crossweight_percent","front_ride_height_in","rear_ride_height_in","rear_trackbar_in"],
    "rear_end": ["diff_preload_ftlbs","gear_note"]
})
LIM = setup_rules.get("limits", {
    "pressure": {"min_psig": 10.0, "max_psig": 60.0, "increments_psig": 0.5},
    "shock_clicks": {"min_clicks": 0, "max_clicks": 10, "increments": 1},
    "spring_rate": {"min_lbin": 100, "max_lbin": 2200, "increments": 25},
    "ride_height": {"min_in": 2.0, "max_in": 6.0, "increments": 0.05},
    "crossweight": {"min_pct": 45.0, "max_pct": 55.0, "increments": 0.1},
    "trackbar": {"min_in": 5.0, "max_in": 12.0, "increments": 0.25},
    "diff_preload": {"min_ftlbs": 0, "max_ftlbs": 75, "increments": 5}
})

# --- helpers
def sev_bucket(n): 
    return "slight" if n <=3 else ("moderate" if n <=7 else "severe")

def mk_delta(name, delta, units):
    sign = "+" if delta > 0 else ""
    return f"{name}: {sign}{delta:g}{units}"

def corner_list_with_meta(track_obj):
    """
    Accepts:
      "corners": ["T1","T2"]   OR
      "corners": [{"name":"T1","dir":"R","bank_deg":7,"angle_deg":90}, ...]
    Returns list of dicts with defaults filled.
    """
    raw = track_obj.get("corners", [])
    out = []
    if not raw:
        return [{"name":"T1","dir":"M","bank_deg":0.0,"angle_deg":90.0}]
    for item in raw:
        if isinstance(item, str):
            out.append({"name": item, "dir": "M", "bank_deg": 0.0, "angle_deg": 90.0})
        elif isinstance(item, dict):
            out.append({
                "name": item.get("name") or item.get("corner") or "Corner",
                "dir": (item.get("dir") or item.get("direction") or "M").upper()[0],  # L/R/M
                "bank_deg": float(item.get("bank_deg", 0.0) or 0.0),
                "angle_deg": float(item.get("angle_deg", 90.0) or 90.0),
            })
    return out

def bank_factor(bank_deg: float):
    # flat corners need bigger changes; high bank need smaller
    if bank_deg <= 4: return 1.25
    if bank_deg <= 12: return 1.0
    return 0.8

def angle_factor(angle_deg: float):
    # hairpins/long sweepers need larger steps than quick bends
    if angle_deg >= 120: return 1.25
    if angle_deg >= 60: return 1.0
    return 0.85

def scale_deltas_in_strings(sugg_dict, factor):
    """Multiply numeric deltas inside suggestion strings by factor and snap to proper step size."""
    def step_for_param(pname: str):
        pname = pname.lower()
        if "pressure" in pname: return LIM.get("pressure", {}).get("increments_psig", 0.5)
        if "shock" in pname and "click" in pname: return LIM.get("shock_clicks", {}).get("increments", 1)
        if "spring_rate" in pname: return LIM.get("spring_rate", {}).get("increments", 25)
        if "crossweight" in pname: return LIM.get("crossweight", {}).get("increments", 0.1)
        if "trackbar" in pname: return LIM.get("trackbar", {}).get("increments", 0.25)
        if "ride_height" in pname: return LIM.get("ride_height", {}).get("increments", 0.05)
        if "diff_preload" in pname: return LIM.get("diff_preload", {}).get("increments", 5)
        return 1.0

    def scale_one(txt: str):
        try:
            param = txt.split(":",1)[0]
            step = step_for_param(param)
            m = re.search(r"([+-]?\d+(\.\d+)?)", txt)
            if not m:
                return txt
            val = float(m.group(1)) * factor
            snapped = round(val / step) * step
            new_num = f"{snapped:g}"
            start, end = m.span(1)
            new_txt = txt[:start] + new_num + txt[end:]
            return new_txt
        except Exception:
            return txt

    return {k: [scale_one(x) for x in v] for k, v in sugg_dict.items()}

def mirror_sides(suggestions_dict):
    """Swap LF<->RF and LR<->RR in suggestion strings for right-hand corners."""
    def swap_one(txt):
        txt = txt.replace("LF_", "__TMP_F__")
        txt = txt.replace("RF_", "LF_")
        txt = txt.replace("__TMP_F__", "RF_")
        txt = txt.replace("LR_", "__TMP_R__")
        txt = txt.replace("RR_", "LR_")
        txt = txt.replace("__TMP_R__", "RR_")
        return txt
        return {k: [swap_one(x) for x in v] for k, v in suggestions_dict.items()}


# ----- SIDEBAR: track + run type -----
with st.sidebar:
    track_names = sorted(list(tracks.keys())) if tracks else ["Unknown Track"]
    idx = track_names.index("Watkins Glen International (Cup)") if "Watkins Glen International (Cup)" in track_names else 0
    track_pick = st.selectbox("Track", track_names, index=idx)
    track_obj = tracks.get(track_pick, {})
    corners_meta = corner_list_with_meta(track_obj)
    run_type = st.radio("Run type", ["Practice","Qualifying","Race"], index=0, horizontal=True)

# ----- CORNER FEEL INPUTS -----
st.header("Corner Feel")
DEFAULT_FEELINGS = [
    "No issue / skip",
    "Loose on entry","Loose mid-corner","Loose on exit",
    "Tight on entry","Tight mid-corner","Tight on exit",
    "Brakes locking","Traction wheelspin","Porpoising / Bottoming","Other"
]

corner_labels = [c["name"] for c in corners_meta]
if "coach_feedback" not in st.session_state or st.session_state.get("_coach_track") != track_pick:
    st.session_state.coach_feedback = {c: {"feels":"No issue / skip","severity":0,"note":""} for c in corner_labels}
    st.session_state._coach_track = track_pick

cols = st.columns(3)
for i, meta in enumerate(corners_meta):
    c = meta["name"]
    with cols[i % 3]:
        dir_label = {"L":"Left","R":"Right","M":"Mixed/Unknown"}.get(meta.get("dir","M"),"Mixed/Unknown")
        st.markdown(f"**{c}**  \n<small>Dir: {dir_label} • Bank: {meta.get('bank_deg',0):g}° • Angle: {meta.get('angle_deg',90):g}°</small>", unsafe_allow_html=True)
        feels = st.selectbox(f"{c} feel", DEFAULT_FEELINGS, index=0, key=f"coach_feel_{re.sub(r'[^a-z0-9]+','_',c.lower())}")
        severity = st.slider(f"{c} severity", 0, 10, st.session_state.coach_feedback[c].get("severity",0), key=f"coach_sev_{re.sub(r'[^a-z0-9]+','_',c.lower())}")
        note = st.text_input(f"{c} note", value=st.session_state.coach_feedback[c].get("note",""), key=f"coach_note_{re.sub(r'[^a-z0-9]+','_',c.lower())}")
        st.session_state.coach_feedback[c] = {"feels": feels, "severity": int(severity), "note": note}

st.markdown("---")
st.caption("Severity: 1–3 slight · 4–7 moderate · 8–10 severe")

# ======== TEMP COMPENSATION ========
st.header("Track Temperature Compensation")
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
    if ad <= 5: return 0
    if ad <= 10: return 1
    if ad <= 20: return 2
    return 3

def suggest_for_temp(baseline, current):
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

    hotter = diff > 0

    for tname in ("LF_pressure","RF_pressure","LR_pressure","RR_pressure"):
        if tname in ALLOWED.get("tires", []):
            delta = -psi_step*scale if hotter else +psi_step*scale
            out["tires"].append(mk_delta(tname, delta, " psi"))

    shock_bump_names = ("LF_shock_bump_clicks","RF_shock_bump_clicks","LR_shock_bump_clicks","RR_shock_bump_clicks")
    for sname in shock_bump_names:
        if sname in ALLOWED.get("suspension", []):
            delta = +shock_step*scale if hotter else -shock_step*scale
            out["suspension"].append(mk_delta(sname, delta, " clicks"))

    if hotter:
        if "rear_spring_rate" in ALLOWED.get("suspension", []):
            out["suspension"].append(mk_delta("rear_spring_rate", +spring_step*scale, " lb/in"))
        if "diff_preload_ftlbs" in ALLOWED.get("rear_end", []):
            out["rear_end"].append(mk_delta("diff_preload_ftlbs", +diff_step*scale, " ft-lbs"))
    else:
        if "diff_preload_ftlbs" in ALLOWED.get("rear_end", []):
            out["rear_end"].append(mk_delta("diff_preload_ftlbs", -diff_step*scale, " ft-lbs"))
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

    # 1) Temp compensation
    temp_out, temp_diff, temp_scale = suggest_for_temp(baseline_temp, current_temp)
    for k in agg:
        agg[k].extend(temp_out[k])

    # 2) Corner-based rules with direction & bank/angle scaling
    for meta in corners_meta:
        corner = meta["name"]
        fb = st.session_state.coach_feedback.get(corner, {"feels":"No issue / skip","severity":0})
        feel = fb["feels"]
        sev = sev_bucket(fb["severity"])
        if feel != "No issue / skip" and fb["severity"] > 0:
            s = suggest_for_symptom(feel, sev)
            fac = bank_factor(meta.get("bank_deg",0.0)) * angle_factor(meta.get("angle_deg",90.0))
            s = scale_deltas_in_strings(s, fac)
            if (meta.get("dir","M").upper().startswith("R")):
                s = mirror_sides(s)
            per_corner.append({"corner": corner, "feel": feel, "severity": sev, "note": fb.get("note",""),
                               "dir": meta.get("dir","M"), "bank_deg": meta.get("bank_deg",0.0),
                               "angle_deg": meta.get("angle_deg",90.0), "factor": fac, "suggestions": s})
            for k in agg:
                agg[k].extend(s[k])

    # --- Output ---
    if temp_scale > 0:
        direction = "hotter" if temp_diff > 0 else "cooler"
        st.info(f"Temp compensation applied: track is {abs(temp_diff)}°F {direction} than baseline (severity x{temp_scale}).")

    if not per_corner and temp_scale == 0:
        st.info("No problems selected and temp is near baseline. Nothing to change.")
    else:
        st.subheader("Key Findings")
        if temp_scale > 0:
            st.write(f"- **Temperature**: {abs(temp_diff)}°F {'hotter' if temp_diff>0 else 'cooler'} than baseline")
        for item in per_corner:
            dir_label = {"L":"Left","R":"Right","M":"Mixed"}[item["dir"][:1].upper()]
            st.write(f"- **{item['corner']}** ({dir_label}; bank {item['bank_deg']:g}°, angle {item['angle_deg']:g}°; scale ×{item['factor']:.2f}): {item['feel']} ({item['severity']})" + (f" — {item['note']}" if item['note'] else ""))

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
        st.write("- **Auto Left/Right**: mirrors LF/RF & LR/RR changes on right-handers so the fix targets the loaded side.")
        st.write("- **Banking/Angle scaling**: bigger steps for flat or hairpin corners; smaller steps for high-banked or quick bends.")
        st.write("- Keep tweaks small and re-test to avoid chasing your tail.")

        st.subheader("Next Run Checklist")
        st.write("- Did each corner with a problem get better?")
        st.write("- Any new side effects elsewhere?")
        st.write("- If still off, take one more step (same direction).")

        plan = {
            "track": track_pick,
            "run_type": run_type,
            "baseline_temp_f": baseline_temp,
            "current_temp_f": current_temp,
            "temp_diff_f": current_temp - baseline_temp,
            "corners_used": per_corner,
            "recommendations": agg,
            "limits": LIM,
        }
        st.download_button("Download plan (.json)", data=json.dumps(plan, indent=2).encode("utf-8"),
                           file_name="setup_coach_plan.json", mime="application/json")
else:
    st.info("Pick corners, set how bad it is, set temps, then hit **Compute Suggestions**.")
