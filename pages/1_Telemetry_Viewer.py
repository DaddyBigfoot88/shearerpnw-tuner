
import io, json, math, os, pathlib, tempfile
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

st.set_page_config(layout="wide")
st.title("📊 Telemetry Viewer (CSV & IBT)")
st.caption("Upload CSV or raw iRacing .ibt. Track map click-to-flag. Suggestions are OPT-IN only.")

# ===== ChatGPT export header (no suggestions unless opt-in + has problem flags) =====
CHATGPT_HEADER = '''(Just paste everything below into ChatGPT and hit Enter.)

=== CHATGPT SETUP COACH INSTRUCTIONS (PASTE THIS WHOLE BLOCK) ===
You are a NASCAR Next Gen setup coach.

IMPORTANT: Only provide setup suggestions if BOTH conditions are true:
- generate_suggestions == true
- There is at least one flag with is_problem == true (either distance flags or map flags).

If the conditions are not met, only acknowledge the data was received and stop.

When suggestions are allowed, follow these rules:
- Use exact, garage-style outputs grouped by Tires, Chassis, Suspension, Rear End.
- Shocks: 0-10 clicks only. Tire pressures: change in 0.5 psi steps. Diff preload: 0-75 ft-lbs. LF caster >= +8.0 degrees.
- If a suggested change conflicts with limits, cap it and say so.
- If track temp is lower than baseline, bias pressures down ~0.5 psi per 10-15 F; higher temps bias up. Then fine-tune by tire edge temps.
- Keep tips short. No fluff.

Output format (only when suggestions are allowed):
1) Key Findings (one line per corner)
2) Setup Changes (garage format, with units and click counts)
3) Why This Helps (one short line each)
4) Next Lap Checklist (what to feel for)

OK—here is the data:

```
{{TELEMETRY_JSON_PASTE_HERE}}
```

End of data.
=== END INSTRUCTIONS ===
'''

DEFAULT_WGI_SEGMENTS = {
    "T1": [0.02, 0.10],
    "T2": [0.18, 0.24],
    "T3": [0.24, 0.28],
    "Bus Stop": [0.43, 0.52],
    "T5": [0.55, 0.63],
    "T6": [0.75, 0.83],
    "T7": [0.88, 0.97]
}

def shaded_corners(fig, segments):
    for label, (x0, x1) in segments.items():
        fig.add_vrect(x0=x0, x1=x1, fillcolor=None, line_width=0,
                      annotation_text=label, annotation_position="top left",
                      opacity=0.08)

def add_flag_rects(fig, flags):
    for f in flags:
        try:
            x0 = float(f["start_pct"]); x1 = float(f["end_pct"])
        except Exception:
            continue
        fig.add_vrect(x0=x0, x1=x1, fillcolor="red", opacity=0.18, line_width=0)

def build_chatgpt_export(summary_dict):
    def round_half_safe(x):
        try:
            f = float(x)
            if math.isfinite(f): return round(f * 2) / 2.0
        except Exception:
            return None
        return None

    pe = summary_dict.get("pressures_ending_psi")
    if isinstance(pe, dict):
        summary_dict["pressures_ending_psi"] = {k: v for k, v in (
            (k, round_half_safe(v)) for k, v in pe.items()
        ) if v is not None}

    # round map coords
    if "user_flags_map" in summary_dict:
        for f in summary_dict["user_flags_map"]:
            for k in ("x_norm","y_norm"):
                try:
                    f[k] = round(float(f.get(k, 0.0)), 4)
                except Exception:
                    f[k] = None

    json_block = json.dumps(summary_dict, indent=2)
    return CHATGPT_HEADER.replace("{{TELEMETRY_JSON_PASTE_HERE}}", json_block)

def coerce_min_columns(df: pd.DataFrame):
    notes = []
    for col in ("Throttle","Brake"):
        if col in df.columns:
            try:
                if float(df[col].max()) <= 1.5:
                    df[col] = (df[col] * 100.0).clip(0,100)
            except Exception: pass

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

    required = {"Speed","Throttle","Brake"}
    missing = sorted(list(required - set(df.columns)))
    if missing: return df, notes, missing
    return df, notes, []

def load_ibt_to_df(uploaded_file):
    try:
        import irsdk
    except Exception:
        st.error("pyirsdk isn't installed on this build. Add 'pyirsdk' and 'PyYAML' to requirements.txt.")
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

        want = ["Lap","LapDistPct","LapDist","Speed","Throttle","Brake",
                "SteeringWheelAngle","YawRate","RRshockVel","CFSRrideHeight",
                "LFpressure","RFpressure","LRpressure","RRpressure",
                "LFrideHeight","RFrideHeight","LRrideHeight","RRrideHeight"]
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

        try:
            if hasattr(ibt, "get_session_info"):
                st.session_state["_session_yaml"] = ibt.get_session_info()
        except Exception: pass

        return df
    finally:
        try:
            if 'ibt' in locals() and hasattr(ibt, "close"): ibt.close()
        except Exception: pass
        try: os.unlink(tmp_path)
        except Exception: pass

# ===== Sidebar =====
with st.sidebar:
    up = st.file_uploader("Upload telemetry (.csv or .ibt)", type=["csv","ibt"])
    track = st.selectbox("Track", ["Watkins Glen International"], index=0)
    view_mode = st.radio("View", ["Per lap", "Whole run"], index=0)
    segs = DEFAULT_WGI_SEGMENTS.copy()
    with st.expander("Adjust corner ranges (LapDistPct)"):
        for k, (a,b) in list(segs.items()):
            a2 = st.slider(f"{k} start", 0.0, 1.0, float(a), 0.005, key=f"{k}_a")
            b2 = st.slider(f"{k} end",   0.0, 1.0, float(b), 0.005, key=f"{k}_b")
            if b2 < a2: b2 = a2 + 0.01
            segs[k] = [a2, b2]
    run_type = st.radio("Run type", ["Qualifying","Short Run","Long Run"], index=1)

if not up:
    st.info("Upload a CSV or IBT with at least Speed, Throttle, and Brake. (Lap/LapDistPct optional; we will synthesize if missing)")
    st.stop()

suffix = pathlib.Path(up.name).suffix.lower()
if suffix == ".csv":
    try: df = pd.read_csv(up)
    except Exception as e:
        st.error(f"Error reading CSV: {e}"); st.stop()
    df, synthesized, missing_core = coerce_min_columns(df)
    if synthesized: st.warning(f"Synthesized columns: {', '.join(synthesized)}")
    if missing_core: st.error(f"Missing core columns: {', '.join(missing_core)}"); st.stop()
elif suffix == ".ibt":
    try: df = load_ibt_to_df(up)
    except Exception as e:
        st.error(f"Failed to parse IBT: {e}"); st.stop()
else:
    st.error("Unsupported file type."); st.stop()

if "Lap" not in df.columns: df["Lap"] = 1
laps = sorted(pd.unique(df["Lap"]).tolist())

# ===== State =====
if "user_flags" not in st.session_state: st.session_state.user_flags = []           # distance-based (LapDistPct ranges)
if "user_flags_map" not in st.session_state: st.session_state.user_flags_map = []   # image-based points
if "click_buffer" not in st.session_state: st.session_state.click_buffer = []

# ===== Tabs =====
tab_map, tab_overview, tab_stb, tab_shocks, tab_all, tab_flags = st.tabs(
    ["Track Map (Click)", "Overview (Heatmap)", "Speed/Throttle/Brake", "Shocks & Heights", "All Channels", "Flags & Export"]
)

# ---------- Track Map (Click) ----------
with tab_map:
    st.subheader("Track Map (click to drop problem markers)")
    left, right = st.columns([3,2])

    with left:
        uploaded_map = st.file_uploader("Optional: Upload a custom track map image (PNG/JPG)", type=["png","jpg","jpeg"], key="map_up")
        if uploaded_map is not None:
            image = Image.open(uploaded_map).convert("RGB")
        else:
            try:
                image = Image.open("assets/track_map_wgi.png").convert("RGB")
            except Exception:
                st.error("Missing assets/track_map_wgi.png. Add a PNG track map to assets/.")
                image = None

        if image is not None:
            w, h = image.size
            figm = go.Figure()
            figm.add_layout_image(dict(source=image, xref="x", yref="y", x=0, y=h, sizex=w, sizey=h, sizing="stretch", layer="below"))
            figm.update_xaxes(visible=False, range=[0, w])
            figm.update_yaxes(visible=False, range=[0, h], scaleanchor="x", scaleratio=1, autorange="reversed")
            if st.session_state.user_flags_map:
                xs = [f["x_px"] for f in st.session_state.user_flags_map]
                ys = [f["y_px"] for f in st.session_state.user_flags_map]
                names = [f.get("type","Flag") for f in st.session_state.user_flags_map]
                figm.add_trace(go.Scatter(x=xs, y=ys, mode="markers+text", text=names, textposition="top center", name="Flags"))
            figm.update_layout(title="Click on the map to add a marker", margin=dict(l=0,r=0,t=30,b=0))

            with st.expander("Click options"):
                st.caption("Clicks place a point. We will store normalized coords (x/W, y/H).")
                flag_type = st.selectbox("Flag type", ["Loose on entry","Loose mid","Loose on exit","Tight on entry","Tight mid","Tight on exit","Other"], key="map_flag_type")
                note = st.text_input("Note (optional)", "", key="map_flag_note")
                is_problem = st.checkbox("Mark as problem", value=True, key="map_is_problem")

            try:
                from streamlit_plotly_events import plotly_events
                clicks = plotly_events(figm, click_event=True, select_event=False, hover_event=False, key="map_clicks")
                if clicks:
                    x = float(clicks[-1]["x"]); y = float(clicks[-1]["y"])
                    x = min(max(x, 0.0), w); y = min(max(y, 0.0), h)
                    st.session_state.user_flags_map.append({
                        "x_px": x, "y_px": y,
                        "x_norm": x/float(w), "y_norm": y/float(h),
                        "type": st.session_state.map_flag_type,
                        "note": st.session_state.map_flag_note,
                        "is_problem": bool(st.session_state.map_is_problem)
                    })
                    st.success(f"Added map flag at ({x:.0f}, {y:.0f}).")
                    figm.add_trace(go.Scatter(x=[x], y=[y], mode="markers+text", text=[st.session_state.map_flag_type], textposition="top center", name="Flag"))
                    figm.update_layout(transition_duration=0)
                    st.plotly_chart(figm, use_container_width=True)
                else:
                    st.plotly_chart(figm, use_container_width=True)
            except Exception as e:
                st.error("To enable map clicks, ensure streamlit-plotly-events is installed (requirements.txt).")
                st.caption(f"Details: {e}")

    with right:
        st.write("Current map flags:")
        if st.session_state.user_flags_map:
            st.dataframe(pd.DataFrame(st.session_state.user_flags_map), use_container_width=True, height=380)
        else:
            st.info("No map flags yet. Click on the image to add some.")
        if st.button("🧹 Clear map flags"):
            st.session_state.user_flags_map = []
            st.info("Map flags cleared.")

# ---------- Overview (Heatmap) ----------
with tab_overview:
    st.subheader("Track Heatmap (Whole Run)")
    bins = np.linspace(0.0, 1.0, 201)
    centers = (bins[:-1] + bins[1:]) / 2.0
    df["bin"] = pd.cut(df["LapDistPct"].clip(0,1), bins, include_lowest=True, labels=False)
    agg = df.groupby("bin").agg(
        speed=("Speed","mean"),
        throttle=("Throttle","mean"),
        brake=("Brake","mean")
    ).reindex(range(len(bins)-1)).fillna(method="ffill").fillna(0)

    z = np.vstack([agg["speed"].values, agg["throttle"].values, agg["brake"].values])
    fig = go.Figure(data=go.Heatmap(z=z, x=centers, y=["Speed","Throttle","Brake"], coloraxis="coloraxis"))
    fig.update_layout(coloraxis=dict(colorbar=dict(title="Value")), xaxis_title="LapDistPct (0 to 1)", yaxis_title="", title="Whole-Run Heatmap (avg per distance bin)")
    add_flag_rects(fig, st.session_state.user_flags); shaded_corners(fig, segs)
    st.plotly_chart(fig, use_container_width=True)

# ---------- STB (Speed/Throttle/Brake) ----------
with tab_stb:
    st.subheader("Speed / Throttle / Brake")
    if view_mode == "Per lap":
        sel_lap = st.selectbox("Select lap", laps, index=0, key="lap_stb")
        plot_df = df[df["Lap"] == sel_lap]
    else:
        plot_df = df.copy()

    fig1 = go.Figure()
    for col, name in [("Speed","Speed (mph)"),("Throttle","Throttle %"),("Brake","Brake %")]:
        if col in plot_df.columns:
            fig1.add_trace(go.Scatter(x=plot_df["LapDistPct"], y=plot_df[col], mode="lines", name=name))
    shaded_corners(fig1, segs); add_flag_rects(fig1, st.session_state.user_flags)
    fig1.update_layout(title=f"{view_mode} - STB vs LapDistPct", xaxis_title="LapDistPct", yaxis_title="Value")
    st.plotly_chart(fig1, use_container_width=True)

# ---------- Shocks & Heights ----------
with tab_shocks:
    st.subheader("Shocks & Ride Heights")
    if view_mode == "Per lap":
        sel_lap2 = st.selectbox("Select lap", laps, index=0, key="lap_shock")
        pdf = df[df["Lap"] == sel_lap2]
    else:
        pdf = df.copy()

    cols = [c for c in ["RRshockVel","CFSRrideHeight","LFrideHeight","RFrideHeight","LRrideHeight","RRrideHeight"] if c in pdf.columns]
    if not cols:
        st.info("No shock/ride height columns found.")
    else:
        for c in cols:
            figx = go.Figure()
            figx.add_trace(go.Scatter(x=pdf["LapDistPct"], y=pdf[c], mode="lines", name=c))
            shaded_corners(figx, segs); add_flag_rects(figx, st.session_state.user_flags)
            figx.update_layout(title=f"{view_mode} - {c} vs LapDistPct", xaxis_title="LapDistPct", yaxis_title=c)
            st.plotly_chart(figx, use_container_width=True)

# ---------- All Channels ----------
with tab_all:
    st.subheader("Graph All Data (pick columns)")
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and c not in ("bin",)]
    defaults = ["Speed","Throttle","Brake"]
    more = sorted([c for c in numeric_cols if c not in defaults + ["Lap","LapDistPct"]])
    choices = st.multiselect("Columns to plot vs LapDistPct", defaults + more, default=defaults)
    if view_mode == "Per lap":
        sel_lap3 = st.selectbox("Select lap", laps, index=0, key="lap_all")
        p3 = df[df["Lap"] == sel_lap3]
    else:
        p3 = df.copy()
    if choices:
        figA = go.Figure()
        for c in choices:
            if c in p3.columns:
                figA.add_trace(go.Scatter(x=p3["LapDistPct"], y=p3[c], mode="lines", name=c))
        shaded_corners(figA, segs); add_flag_rects(figA, st.session_state.user_flags)
        figA.update_layout(title=f"{view_mode} - selected columns vs LapDistPct", xaxis_title="LapDistPct", yaxis_title="Value")
        st.plotly_chart(figA, use_container_width=True)
    st.dataframe(df.head(500), use_container_width=True)

# ---------- Flags & Export ----------
with tab_flags:
    st.subheader("Distance Flags (ranges)")
    col1, col2, col3, col4, col5 = st.columns([1,1,1,1,2])
    with col1:
        start_pct = st.number_input("Start %", min_value=0.0, max_value=1.0, value=0.10, step=0.005, format="%.3f")
    with col2:
        end_pct = st.number_input("End %", min_value=0.0, max_value=1.0, value=0.20, step=0.005, format="%.3f")
    with col3:
        flag_type = st.selectbox("Type", ["Loose on entry","Loose mid","Loose on exit","Tight on entry","Tight mid","Tight on exit","Other"])
    with col4:
        is_problem = st.checkbox("Problem", value=True)
    with col5:
        note = st.text_input("Note (optional)", value="")

    add = st.button("Add distance flag")
    clear = st.button("Clear distance flags")
    if add:
        if end_pct <= start_pct: st.warning("End must be greater than Start.")
        else:
            st.session_state.user_flags.append({"start_pct": float(start_pct), "end_pct": float(end_pct), "type": flag_type, "note": note, "is_problem": bool(is_problem)})
            st.success("Distance flag added.")
    if clear:
        st.session_state.user_flags = []; st.info("Distance flags cleared.")

    if st.session_state.user_flags:
        st.write("Current distance flags:")
        st.dataframe(pd.DataFrame(st.session_state.user_flags), use_container_width=True)

    st.markdown("---")
    st.subheader("Export to ChatGPT")
    generate_suggestions = st.checkbox("Generate setup suggestions (opt-in)", value=False,
                                       help="If off, ChatGPT will just acknowledge the data and stop.")

    summary = {
        "car": "NASCAR Next Gen",
        "track": track,
        "session": {"type": run_type, "view": view_mode, "laps": int(df["Lap"].max() - df["Lap"].min() + 1) if len(laps) else 0},
        "conditions": {"track_temp_F": float(df.get("TrackTemp", pd.Series([np.nan])).iloc[0]) if "TrackTemp" in df.columns else None,
                       "baseline_temp_F": 85},
        "pressures_ending_psi": {k: float(df[k].iloc[-1]) for k in ["LFpressure","RFpressure","LRpressure","RRpressure"] if k in df.columns},
        "ride_heights_in": {k: float(df[k].median()) for k in ["CFSRrideHeight","LFrideHeight","RFrideHeight","LRrideHeight","RRrideHeight"] if k in df.columns},
        "corner_findings": [],
        "user_flags": st.session_state.user_flags,
        "user_flags_map": st.session_state.user_flags_map,
        "generate_suggestions": bool(generate_suggestions)
    }

    export_text = build_chatgpt_export(summary)
    st.download_button("Download export (.txt)", data=export_text.encode("utf-8"),
                       file_name="chatgpt_export.txt", mime="text/plain")
    st.text_area("Preview", export_text, height=260)
