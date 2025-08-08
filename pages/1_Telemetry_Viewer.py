# Telemetry Viewer – NO AUTO FETCH, AI export now includes tracks_meta + coach_rules + temps + stats
import io, json, os, pathlib, tempfile, re, mimetypes
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

st.set_page_config(layout="wide")
st.title("Telemetry Viewer")
st.caption("Maps show only if already cached. No auto-download or prefetch. AI export now packs metadata + temps + stats.")

def slug(s: str):
    return re.sub(r'[^a-z0-9_]+', '_', s.lower())

TRACKS_JSON_PATH = pathlib.Path("ShearerPNW_Easy_Tuner_Editables/tracks.json")
TRACKS_META_PATH = pathlib.Path("ShearerPNW_Easy_Tuner_Editables/tracks_meta.json")
COACH_RULES_PATH = pathlib.Path("ShearerPNW_Easy_Tuner_Editables/coach_rules.json")
ASSETS_DIR = pathlib.Path("assets/tracks")
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

def load_json(path, fallback):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:
        st.error("Error reading {}: {}".format(path, e))
    return fallback

def load_tracks():
    if not TRACKS_JSON_PATH.exists():
        st.error("Missing ShearerPNW_Easy_Tuner_Editables/tracks.json")
        return {}
    try:
        return json.loads(TRACKS_JSON_PATH.read_text())
    except Exception as e:
        st.error(f"tracks.json error: {e}")
        return {}

# ---------- NO AUTO FETCH ----------
tracks      = load_tracks()
tracks_meta = load_json(TRACKS_META_PATH, {})
coach_rules = load_json(COACH_RULES_PATH, {})

# Sidebar (kept the same)
with st.sidebar:
    track_names = sorted(list(tracks.keys())) if tracks else ["Unknown Track"]
    default_idx = track_names.index("Watkins Glen International (Cup)") if "Watkins Glen International (Cup)" in track_names else 0
    track_pick = st.selectbox("Track", track_names, index=default_idx)
    track_info = tracks.get(track_pick, {"id":"unknown","corners": ["T1","T2","T3"]})
    up = st.file_uploader("Upload telemetry (.csv or .ibt)", type=["csv","ibt"])
    show_charts = st.checkbox("Show graphs", value=False)
    show_all_table = st.checkbox("Show full raw table", value=False)
    run_type = st.radio("Run type", ["Practice","Qualifying","Race"], index=0, horizontal=True)

# Track image (local-only)
colA, colB = st.columns([1.2, 1.8])
with colA:
    st.subheader("Track")
    img_path = track_info.get("image")
    if img_path and pathlib.Path(img_path).exists():
        st.image(img_path, use_container_width=True, caption=str(track_pick))
    else:
        st.warning("No cached image for this track. Add a file path in tracks.json and commit the image to assets/tracks/.")

# Channels & telemetry loader
with colB:
    st.subheader("Channels and File info")
    df = None
    def coerce_min_columns(df):
        notes = []
        for col in ("Throttle","Brake"):
            if col in df.columns:
                try:
                    if float(df[col].max()) <= 1.5:
                        df[col] = (df[col] * 100.0).clip(0,100)
                except Exception:
                    pass
        if "Lap" not in df.columns:
            df["Lap"] = 1; notes.append("Lap")
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

    if up is not None:
        suffix = pathlib.Path(up.name).suffix.lower()
        if suffix == ".csv":
            try:
                df = pd.read_csv(up)
            except Exception as e:
                st.error(f"CSV read error: {e}")
        elif suffix == ".ibt":
            try:
                import irsdk, tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".ibt") as tmp:
                    tmp.write(up.read()); tmp_path = tmp.name
                ibt = None
                if hasattr(irsdk, "IBT"): ibt = irsdk.IBT(tmp_path)
                elif hasattr(irsdk, "ibt"): ibt = irsdk.ibt.IBT(tmp_path)
                if ibt is None: raise RuntimeError("pyirsdk.IBT class not found")
                try:
                    if hasattr(ibt, "open"): ibt.open()
                except Exception:
                    pass
                want = ["Lap","LapDistPct","LapDist","Speed","Throttle","Brake","SteeringWheelAngle","YawRate"]
                data = {}
                for ch in want:
                    arr = None
                    for getter in ("get","get_channel","get_channel_data_by_name"):
                        try:
                            fn = getattr(ibt, getter); maybe = fn(ch)
                            if maybe is not None: arr = maybe; break
                        except Exception:
                            continue
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
            except Exception as e:
                st.error(f"IBT parse error: {e}")
            finally:
                try:
                    if 'ibt' in locals() and hasattr(ibt, "close"): ibt.close()
                except Exception: pass
                try: os.unlink(tmp_path)
                except Exception: pass

    if df is not None:
        df, notes = coerce_min_columns(df)
        if notes: st.warning("Synthesized columns: " + ", ".join(notes))
        st.write(", ".join(list(df.columns)))

# Quick channel stats (used in AI export too)
def basic_channel_stats(df, cols):
    out = {}
    for c in cols:
        try:
            s = df[c].astype(float)
            out[c] = {
                "count": int(s.shape[0]),
                "min": float(np.nanmin(s)),
                "max": float(np.nanmax(s)),
                "mean": float(np.nanmean(s))
            }
        except Exception:
            continue
    return out

# Graphs (distinct colors)
st.markdown("---")
if show_charts and 'df' in locals() and df is not None:
    st.subheader("Graphs (pick any numeric channels)")
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
        palette = (px.colors.qualitative.Safe + px.colors.qualitative.Set2 + px.colors.qualitative.Plotly)
        color_cycle = palette * 5
        trace_idx = 0
        if selected:
            if bylap and "Lap" in df.columns:
                laps = sorted(pd.unique(df["Lap"]).tolist())
                chosen_laps = st.multiselect("Which laps?", laps, default=laps[:min(3,len(laps))])
            else:
                chosen_laps = [None]
            for ch in selected:
                st.markdown("**{}**".format(ch))
                fig = go.Figure()
                if chosen_laps == [None]:
                    x = df["LapDistPct"] if mode=="LapDistPct" and "LapDistPct" in df.columns else np.arange(len(df))
                    fig.add_trace(go.Scatter(x=x, y=df[ch], mode="lines", name=ch,
                                             line=dict(width=2.5, color=color_cycle[trace_idx % len(color_cycle)]),
                                             opacity=0.95))
                    trace_idx += 1
                else:
                    for L in chosen_laps:
                        dlap = df[df["Lap"]==L]
                        x = dlap["LapDistPct"] if mode=="LapDistPct" and "LapDistPct" in dlap.columns else np.arange(len(dlap))
                        fig.add_trace(go.Scatter(x=x, y=dlap[ch], mode="lines", name="Lap {}".format(L),
                                                 line=dict(width=2.5, color=color_cycle[trace_idx % len(color_cycle)]),
                                                 opacity=0.95))
                        trace_idx += 1
                fig.update_layout(template="plotly_white", xaxis_title=mode, yaxis_title=ch,
                                  legend_orientation="h", legend_y=-0.25, margin=dict(t=30,b=50),
                                  hovermode="x unified", height=300)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Pick at least one channel to plot.")

# Full table
if show_all_table and 'df' in locals() and df is not None:
    st.markdown("---")
    st.subheader("All data table (first 1,000 rows)")
    st.dataframe(df.head(1000), use_container_width=True)

# Corner feedback
st.markdown("---")
st.header("Corner Feedback")
corner_labels = tracks.get(track_pick, {}).get("corners", ["T1","T2","T3"])
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
        st.markdown("**{}**".format(c))
        feels = st.selectbox("{} feel".format(c), DEFAULT_FEELINGS, index=0, key="feel_{}".format(slug(c)))
        severity = st.slider("{} severity".format(c), 0, 10, st.session_state.driver_feedback[c].get("severity",0), key="sev_{}".format(slug(c)))
        note = st.text_input("{} note (optional)".format(c), value=st.session_state.driver_feedback[c].get("note",""), key="note_{}".format(slug(c)))
        st.session_state.driver_feedback[c] = {"feels": feels, "severity": int(severity), "note": note}

st.success("Feedback saved for this track.")

# Setup entry/upload
st.markdown("---")
st.header("Current Setup")
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
            sdf = pd.read_csv(sup)
            st.session_state.setup_current["uploaded_csv"] = sdf.to_dict(orient="list"); st.success("Loaded CSV setup.")
        else:
            st.session_state.setup_current["uploaded_raw"] = sup.read().decode("utf-8", errors="ignore"); st.success("Attached raw text setup (not parsed).")
    except Exception as e:
        st.error(f"Setup upload error: {e}")

# === NEW: Temperature fields for export ===
st.markdown("---")
st.header("Session Temps (for AI export)")
base_default = tracks_meta.get(track_pick, {}).get("baseline_temp_f", coach_rules.get("defaults", {}).get("baseline_temp_f", 85))
c1t, c2t = st.columns(2)
with c1t:
    baseline_temp = st.number_input("Baseline Setup Temperature (°F)", 40, 150, int(base_default))
with c2t:
    current_temp = st.number_input("Current Track Temperature (°F)", 40, 150, int(base_default))

# Export block
st.markdown("---")
st.header("Export to ChatGPT (with rules + track meta + temps + stats)")
generate_suggestions = st.checkbox("Allow setup suggestions (opt-in)", value=False)
is_problem = st.checkbox("This run has real problems", value=False)

rules_path = pathlib.Path("ShearerPNW_Easy_Tuner_Editables/setup_rules_nextgen.json")
if not rules_path.exists():
    st.error("Missing ShearerPNW_Easy_Tuner_Editables/setup_rules_nextgen.json")
else:
    setup_rules = json.loads(rules_path.read_text())

    # Pack a slim copy of coach rules (the engine rules used by the Coach page)
    coach_rules_slim = {
        "run_type_scaling": coach_rules.get("run_type_scaling", {}),
        "feel_key_map": coach_rules.get("feel_key_map", {}),
        "scaling": coach_rules.get("scaling", {}),
        "temp_comp": coach_rules.get("temp_comp", {}),
        # full symptoms can be big; include if you want stricter guidance:
        "symptoms": coach_rules.get("symptoms", {})
    }

    # Selected track meta (left/right, banking, angle) if available
    track_meta_pick = tracks_meta.get(track_pick, {})

    # Telemetry stats (keep it short + numeric)
    if 'df' in locals() and df is not None:
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        # only summarize up to 14 columns to keep export compact
        summarize_cols = numeric_cols[:14]
        telemetry_stats = basic_channel_stats(df, summarize_cols)
        telem_cols = list(df.columns)
    else:
        telemetry_stats = {}
        telem_cols = []

    CHATGPT_HEADER = """(Paste this whole block into ChatGPT and press Enter.)

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

Extra context you can use:
- run_type_scaling modifies how aggressive the changes should be.
- tracks_meta gives corner direction (L/R), banking (deg), and corner angle (deg) so you can mirror left/right correctly and scale for long/steep corners.
- temp_comp tells you what to bias when track is hotter/cooler than baseline.
- telemetry_stats are just a quick look (min/max/mean) to ground any comments.

Output format (when suggestions are allowed):
1) Key Findings (one line per corner with a problem)
2) Setup Changes (grouped by Tires, Chassis, Suspension, Rear End; include units & clicks)
3) Why This Helps (short reasons)
4) Next Run Checklist (what to feel for)

SESSION CONTEXT:
car: NASCAR Next Gen
track: {{TRACK_NAME}}
run_type: {{RUN_TYPE}}
baseline_setup_temp_f: {{BASE_TEMP}}
current_track_temp_f: {{CUR_TEMP}}

corner_labels: {{CORNER_LABELS_JSON}}

OK—here is the data:

corner_feedback_json = 
```json
{{CORNER_FEEDBACK_JSON}}
```

tracks_meta_for_this_track =
```json
{{TRACK_META_JSON}}
```

coach_rules_core =
```json
{{COACH_RULES_JSON}}
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

telemetry_stats_quicklook =
```json
{{TELEM_STATS_JSON}}
```

gates = {"generate_suggestions": {{GATE_GEN}}, "is_problem": {{GATE_PROB}}}

End of data.
=== END INSTRUCTIONS ===
"""

    export_text = (
        CHATGPT_HEADER
        .replace("{{TRACK_NAME}}", json.dumps(track_pick))
        .replace("{{RUN_TYPE}}", json.dumps(run_type))
        .replace("{{BASE_TEMP}}", json.dumps(baseline_temp))
        .replace("{{CUR_TEMP}}", json.dumps(current_temp))
        .replace("{{CORNER_LABELS_JSON}}", json.dumps(tracks.get(track_pick, {}).get("corners", []), indent=2))
        .replace("{{TRACK_META_JSON}}", json.dumps(track_meta_pick, indent=2))
        .replace("{{COACH_RULES_JSON}}", json.dumps(coach_rules_slim, indent=2))
        .replace("{{CORNER_FEEDBACK_JSON}}", json.dumps(st.session_state.driver_feedback, indent=2))
        .replace("{{SETUP_RULES_JSON}}", json.dumps(setup_rules, indent=2))
        .replace("{{SETUP_CURRENT_JSON}}", json.dumps(st.session_state.setup_current, indent=2))
        .replace("{{TELEM_COLS_JSON}}", json.dumps(telem_cols, indent=2))
        .replace("{{TELEM_STATS_JSON}}", json.dumps(telemetry_stats, indent=2))
        .replace("{{GATE_GEN}}", "true" if generate_suggestions else "false")
        .replace("{{GATE_PROB}}", "true" if is_problem else "false")
    )

    st.download_button("Download ChatGPT export (.txt)",
                       data=export_text.encode("utf-8"),
                       file_name="chatgpt_trackaware_export.txt",
                       mime="text/plain")
    st.text_area("Preview", export_text, height=360)
