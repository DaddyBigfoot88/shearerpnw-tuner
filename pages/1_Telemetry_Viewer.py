
import io, json, os, pathlib, tempfile, math, re
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

st.set_page_config(layout="wide")
st.title("📊 Telemetry Viewer — All NASCAR Tracks")
st.caption("Track-aware corner names, placeholder maps, full data view, channel plotting, setup entry/upload, and strict ChatGPT export.")

def slug(s: str):
    return re.sub(r'[^a-z0-9_]+', '_', s.lower())

# ===== Helpers =====
def coerce_min_columns(df: pd.DataFrame):
    notes = []
    for col in ("Throttle","Brake"):
        if col in df.columns:
            try:
                if float(df[col].max()) <= 1.5:
                    df[col] = (df[col] * 100.0).clip(0,100)
            except Exception: 
                pass
    if "Lap" not in df.columns:
        df["Lap"] = 1
        notes.append("Lap")
    if "LapDistPct" not in df.columns:
        if "LapDist" in df.columns and df["LapDist"].max() > 0:
            df["LapDistPct"] = df["LapDist"] / df.groupby("Lap")["LapDist"].transform("max").replace(0,1)
        else:
            df["_idx"] = df.groupby("Lap").cumcount()
            max_idx = df.groupby("Lap")["_idx"].transform("max").replace(0,1)
            df["LapDistPct"] = df["_idx"] / max_idx
            df.drop(columns=["_idx"], inplace=True)
        notes.append("LapDistPct")
    return df, notes

def load_ibt_to_df(uploaded_file):
    try:
        import irsdk
    except Exception:
        st.error("pyirsdk isn't installed in this build. Add 'pyirsdk' and 'PyYAML' to requirements.txt.")
        raise
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ibt") as tmp:
        tmp.write(uploaded_file.read()); tmp_path = tmp.name
    try:
        ibt = None
        if hasattr(irsdk, "IBT"): ibt = irsdk.IBT(tmp_path)
        elif hasattr(irsdk, "ibt"): ibt = irsdk.ibt.IBT(tmp_path)
        if ibt is None: raise RuntimeError("pyirsdk.IBT class not found")
        try:
            if hasattr(ibt, "open"): ibt.open()
        except Exception: pass
        want = ["Lap","LapDistPct","LapDist","Speed","Throttle","Brake","SteeringWheelAngle","YawRate"]
        data = {}
        for ch in want:
            arr = None
            for getter in ("get","get_channel","get_channel_data_by_name"):
                try:
                    fn = getattr(ibt, getter); maybe = fn(ch)
                    if maybe is not None: arr = maybe; break
                except Exception: continue
            if arr is not None: data[ch] = arr
        if not data: raise RuntimeError("No known channels found in IBT.")
        df = pd.DataFrame(data).dropna(how="all")
        for col in ("Throttle","Brake"):
            if col in df.columns and df[col].max() <= 1.5:
                df[col] = (df[col] * 100.0).clip(0,100)
        if "LapDistPct" not in df.columns:
            if "LapDist" in df.columns and df["LapDist"].max() > 0:
                if "Lap" not in df.columns: df["Lap"] = 1
                else: df["Lap"] = df["Lap"].fillna(method="ffill").fillna(1).astype(int)
                df["LapDistPct"] = df["LapDist"] / df.groupby("Lap")["LapDist"].transform("max").replace(0,1)
            else:
                if "Lap" not in df.columns: df["Lap"] = 1
                df["_idx"] = df.groupby("Lap").cumcount()
                max_idx = df.groupby("Lap")["_idx"].transform("max").replace(0,1)
                df["LapDistPct"] = df["_idx"] / max_idx
                df.drop(columns=["_idx"], inplace=True)
        return df
    finally:
        try:
            if 'ibt' in locals() and hasattr(ibt, "close"): ibt.close()
        except Exception: pass
        try: os.unlink(tmp_path)
        except Exception: pass

def load_tracks():
    p = pathlib.Path("ShearerPNW_Easy_Tuner_Editables/tracks.json")
    if not p.exists():
        st.error("Missing ShearerPNW_Easy_Tuner_Editables/tracks.json")
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:
        st.error(f"tracks.json error: {e}")
        return {}

# ===== Sidebar =====
with st.sidebar:
    tracks = load_tracks()
    track_names = sorted(list(tracks.keys())) if tracks else ["Unknown Track"]
    default_idx = track_names.index("Watkins Glen International (Cup)") if "Watkins Glen International (Cup)" in track_names else 0
    track_pick = st.selectbox("Track", track_names, index=default_idx)
    track_info = tracks.get(track_pick, {"corners": ["T1","T2","T3"]})
    st.caption("Corner list is track-specific. Edit tracks.json to add or fix names.")

    up = st.file_uploader("Upload telemetry (.csv or .ibt)", type=["csv","ibt"])    
    show_charts = st.checkbox("Show graphs", value=False)
    show_all_table = st.checkbox("Show full raw table", value=False)
    run_type = st.radio("Run type", ["Practice","Qualifying","Race"], index=0, horizontal=True)
    baseline_temp = st.number_input("Baseline setup temp (°F)", 50, 140, 85)
    current_temp = st.number_input("Current track temp (°F)", 50, 140, 90)

# Track image + channels
colA, colB = st.columns([1.6, 2.4])
with colA:
    st.subheader("Track Guide")
    img_path = track_info.get("image")
    if img_path and pathlib.Path(img_path).exists():
        st.image(img_path, use_column_width=True, caption=f"{track_pick}")
    else:
        st.info("No track image found. Drop a PNG/JPG at the path in tracks.json to show a corner guide.")

# ===== Load telemetry =====
df = None
if up is not None:
    suffix = pathlib.Path(up.name).suffix.lower()
    if suffix == ".csv":
        try: df = pd.read_csv(up)
        except Exception as e: st.error(f"CSV read error: {e}")
    elif suffix == ".ibt":
        try: df = load_ibt_to_df(up)
        except Exception as e: st.error(f"IBT parse error: {e}")
    if df is not None:
        df, synthesized = coerce_min_columns(df)
        if synthesized: st.warning("Synthesized columns: " + ", ".join(synthesized))

with colB:
    st.subheader("Channels found")
    if df is None: st.caption("Upload a file to see channels.")
    else: st.write(", ".join(list(df.columns)))

# ===== Graphing =====
if show_charts and df is not None:
    st.markdown("---"); st.subheader("Graphs (pick any numeric channels)")
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        st.info("No numeric columns to plot.")
    else:
        filter_text = st.text_input("Filter channels (contains)", "")
        if filter_text:
            numeric_cols = [c for c in numeric_cols if filter_text.lower() in c.lower()]
        default_pick = [c for c in ["Speed","Throttle","Brake","SteeringWheelAngle"] if c in numeric_cols][:3]
        selected = st.multiselect("Channels to plot", numeric_cols, default=default_pick)
        mode = st.radio("X axis", ["LapDistPct","Index"], index=0, horizontal=True)
        bylap = st.checkbox("Split by Lap", value=True)
        if selected:
            if bylap and "Lap" in df.columns:
                laps = sorted(pd.unique(df["Lap"]).tolist())
                chosen_laps = st.multiselect("Which laps?", laps, default=laps[:min(3,len(laps))])
            else:
                chosen_laps = [None]
            for ch in selected:
                st.markdown(f"**{ch}**")
                fig = go.Figure()
                if chosen_laps == [None]:
                    x = df["LapDistPct"] if mode=="LapDistPct" and "LapDistPct" in df.columns else np.arange(len(df))
                    fig.add_trace(go.Scatter(x=x, y=df[ch], mode="lines", name=ch))
                else:
                    for L in chosen_laps:
                        dlap = df[df["Lap"]==L]
                        x = dlap["LapDistPct"] if mode=="LapDistPct" and "LapDistPct" in dlap.columns else np.arange(len(dlap))
                        fig.add_trace(go.Scatter(x=x, y=dlap[ch], mode="lines", name=f"Lap {L}"))
                fig.update_layout(xaxis_title=mode, yaxis_title=ch, height=280)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Pick at least one channel to graph.")

# ===== All data table =====
if show_all_table and df is not None:
    st.markdown("---"); st.subheader("All data table (first 1,000 rows)")
    st.dataframe(df.head(1000), use_container_width=True)

# ===== Corner Feedback =====
st.markdown("---")
st.header("🧭 Corner Feedback — track-matched labels")
corner_labels = track_info.get("corners", ["T1","T2","T3"])
if "driver_feedback" not in st.session_state or st.session_state.get("_fb_track") != track_pick:
    st.session_state.driver_feedback = {c: {"feels":"No issue / skip","severity":0,"note":""} for c in corner_labels}
    st.session_state._fb_track = track_pick

cols = st.columns(3)
DEFAULT_FEELINGS = [
    "No issue / skip",
    "Loose on entry","Loose mid-corner","Loose on exit",
    "Tight on entry","Tight mid-corner","Tight on exit",
    "Understeer everywhere","Oversteer everywhere",
    "Porpoising / Bottoming","Brakes locking","Traction wheelspin","Other"]
for i, c in enumerate(corner_labels):
    with cols[i % 3]:
        st.markdown(f"**{c}**")
        feels = st.selectbox(f"{c} feel", DEFAULT_FEELINGS, index=0, key=f"feel_{slug(c)}")
        severity = st.slider(f"{c} severity", 0, 10, st.session_state.driver_feedback[c].get("severity",0), key=f"sev_{slug(c)}")
        note = st.text_input(f"{c} note (optional)", value=st.session_state.driver_feedback[c].get("note",""), key=f"note_{slug(c)}")
        st.session_state.driver_feedback[c] = {"feels": feels, "severity": int(severity), "note": note}

st.success("Feedback saved for this track.")

# ===== Setup entry / upload =====
st.markdown("---"); st.header("🛠️ Current Setup — enter or upload")
if "setup_current" not in st.session_state: st.session_state.setup_current = {}
c1, c2, c3, c4 = st.columns(4)
with c1:
    LFp = st.number_input("LF pressure", 5.0, 80.0, 22.0, 0.5)
    LRp = st.number_input("LR pressure", 5.0, 80.0, 22.0, 0.5)
with c2:
    RFp = st.number_input("RF pressure", 5.0, 80.0, 22.0, 0.5)
    RRp = st.number_input("RR pressure", 5.0, 80.0, 22.0, 0.5)
with c3:
    xwt = st.number_input("Crossweight %", 40.0, 60.0, 50.0, 0.1)
    tb = st.number_input("Rear trackbar (in)", 3.0, 14.0, 8.0, 0.25)
with c4:
    dp = st.number_input("Diff preload (ft-lbs)", 0, 100, 40, 5)
    gear_note = st.text_input("Gear note", "N/A")

st.session_state.setup_current.update({
    "tires": {"LF":LFp, "RF":RFp, "LR":LRp, "RR":RRp},
    "chassis": {"crossweight_percent": xwt, "rear_trackbar_in": tb},
    "rear_end": {"diff_preload_ftlbs": dp, "gear_note": gear_note}
})

sup = st.file_uploader("Upload setup", type=["json","csv","sto","txt"], key="setup_up")
if sup is not None:
    suf = pathlib.Path(sup.name).suffix.lower()
    try:
        if suf == ".json":
            st.session_state.setup_current["uploaded_json"] = json.load(sup); st.success("Loaded JSON setup.")
        elif suf == ".csv":
            import pandas as pd; sdf = pd.read_csv(sup)
            st.session_state.setup_current["uploaded_csv"] = sdf.to_dict(orient="list"); st.success("Loaded CSV setup.")
        else:
            st.session_state.setup_current["uploaded_raw"] = sup.read().decode("utf-8", errors="ignore"); st.success("Attached raw text setup (not parsed)." )
    except Exception as e:
        st.error(f"Setup upload error: {e}")

# ===== Export =====
st.markdown("---"); st.header("📤 Export to ChatGPT (with rules, no auto suggestions)")
generate_suggestions = st.checkbox("✅ Allow setup suggestions (opt-in)", value=False)
is_problem = st.checkbox("This run has real problems", value=False)

rules_path = pathlib.Path("ShearerPNW_Easy_Tuner_Editables/setup_rules_nextgen.json")
tracks_path = pathlib.Path("ShearerPNW_Easy_Tuner_Editables/tracks.json")
if not all([rules_path.exists(), tracks_path.exists()]):
    st.error("Missing setup_rules_nextgen.json or tracks.json in ShearerPNW_Easy_Tuner_Editables/")
else:
    setup_rules = json.loads(rules_path.read_text())
    tracks_json = json.loads(tracks_path.read_text())

    CHATGPT_HEADER = '''(Paste this whole block into ChatGPT and press Enter.)

=== CHATGPT SETUP COACH (TRACK-AWARE FEEDBACK) ===
You are a NASCAR Next Gen setup coach.

ONLY provide setup suggestions if BOTH are true:
- generate_suggestions == true
- is_problem == true
Otherwise, acknowledge the data and stop.

Rules you must follow:
- Use ONLY parameters listed under setup_rules.allowed_parameters.
- Respect hard ranges and increments in setup_rules.limits. If a suggestion would go out of bounds, clamp to the nearest allowed value and say you clamped it.
- Shocks: clicks are integers within min_clicks..max_clicks.
- Tire pressures: change in increments_psig (e.g., 0.5 psi). Never go below min_psig or above max_psig.
- Diff preload: use only values between min_ftlbs and max_ftlbs.
- Ride heights, cambers, toes: stay within listed bounds and increments.
- Do not invent settings or parts that are not in setup_rules.
- Keep the output short and practical.

Output format (when suggestions are allowed):
1) Key Findings (one line per corner with a problem)
2) Setup Changes (grouped by Tires, Chassis, Suspension, Rear End; include units & clicks)
3) Why This Helps (short reasons)
4) Next Run Checklist (what to feel for)

SESSION CONTEXT:
car: NASCAR Next Gen
track: {{TRACK_NAME}}
run_type: {{RUN_TYPE}}
temps: {"baseline_F": {{BASELINE}}, "current_F": {{CURRENT}}}

corner_labels: {{CORNER_LABELS_JSON}}

OK—here is the data:

corner_feedback_json = 
```json
{{CORNER_FEEDBACK_JSON}}
```

setup_rules = 
```json
{{SETUP_RULES_JSON}}
```

setup_current = 
```json
{{SETUP_CURRENT_JSON}}
```

telemetry_columns_present = 
```json
{{TELEM_COLS_JSON}}
```

gates = {"generate_suggestions": {{GATE_GEN}}, "is_problem": {{GATE_PROB}}}

End of data.
=== END INSTRUCTIONS ===
'''

    telem_cols = list(df.columns) if df is not None else []
    export_text = (
        CHATGPT_HEADER
        .replace("{{TRACK_NAME}}", json.dumps(track_pick))
        .replace("{{RUN_TYPE}}", json.dumps(run_type))
        .replace("{{BASELINE}}", json.dumps(baseline_temp))
        .replace("{{CURRENT}}", json.dumps(current_temp))
        .replace("{{CORNER_LABELS_JSON}}", json.dumps(corner_labels, indent=2))
        .replace("{{CORNER_FEEDBACK_JSON}}", json.dumps(st.session_state.driver_feedback, indent=2))
        .replace("{{SETUP_RULES_JSON}}", json.dumps(setup_rules, indent=2))
        .replace("{{SETUP_CURRENT_JSON}}", json.dumps(st.session_state.setup_current, indent=2))
        .replace("{{TELEM_COLS_JSON}}", json.dumps(telem_cols, indent=2))
        .replace("{{GATE_GEN}}", "true" if generate_suggestions else "false")
        .replace("{{GATE_PROB}}", "true" if is_problem else "false")
    )

    st.download_button("Download ChatGPT export (.txt)",
                       data=export_text.encode("utf-8"),
                       file_name="chatgpt_trackaware_export.txt",
                       mime="text/plain")
    st.text_area("Preview", export_text, height=360)
