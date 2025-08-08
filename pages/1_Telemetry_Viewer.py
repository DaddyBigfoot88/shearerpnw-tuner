
import json, math, os, pathlib, tempfile
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(layout="wide")
st.title("📊 Telemetry Viewer (CSV & IBT)")
st.caption("Upload a CSV or raw iRacing .ibt. New: heatmap, tabs, user flags go into the ChatGPT export.")

CHATGPT_HEADER = """(Just paste everything below into ChatGPT and hit Enter.)

=== CHATGPT SETUP COACH INSTRUCTIONS (PASTE THIS WHOLE BLOCK) ===
You are a NASCAR Next Gen setup coach. Analyze the telemetry summary and give setup changes.

Rules you must follow:
- Use exact, garage-style outputs grouped by Tires, Chassis, Suspension, Rear End.
- Shocks: 0–10 clicks only. Tire pressures: change in 0.5 psi steps. Diff preload: 0–75 ft-lbs. LF caster ≥ +8.0°.
- If a suggested change conflicts with limits, cap it and say so.
- If track temp is lower than baseline, bias pressures down ~0.5 psi per 10–15°F; higher temps bias up. Then fine-tune by tire edge temps.
- Keep tips short. No fluff.

Output format:
1) Key Findings (one line per corner)
2) Setup Changes (garage format, with units and click counts)
3) Why This Helps (one short line each)
4) Next Lap Checklist (what to feel for)

CAR & SESSION CONTEXT:
- Car: NASCAR Next Gen
- Session type: from JSON
- Track: from JSON

OK—here is the data:

```
{{TELEMETRY_JSON_PASTE_HERE}}
```

End of data. Now give setup changes.
=== END INSTRUCTIONS ===
"""

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

    if "user_flags" in summary_dict:
        for f in summary_dict["user_flags"]:
            for k in ("start_pct","end_pct"):
                try:
                    f[k] = round(float(f.get(k, 0.0)), 3)
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
    st.info("Upload a CSV or IBT with at least Speed, Throttle, and Brake. (Lap/LapDistPct optional; we’ll synthesize if missing)")
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

if "user_flags" not in st.session_state: st.session_state.user_flags = []

tab_overview, tab_stb, tab_shocks, tab_all, tab_flags = st.tabs(
    ["Overview (Heatmap)", "Speed/Throttle/Brake", "Shocks & Heights", "All Channels", "Flags & Export"]
)

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
    fig.update_layout(coloraxis=dict(colorbar=dict(title="Value")), xaxis_title="LapDistPct (0 → 1)", yaxis_title="", title="Whole-Run Heatmap (avg per distance bin)")
    add_flag_rects(fig, st.session_state.user_flags); shaded_corners(fig, segs)
    st.plotly_chart(fig, use_container_width=True)

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
    fig1.update_layout(title=f"{view_mode} – STB vs LapDistPct", xaxis_title="LapDistPct", yaxis_title="Value")
    st.plotly_chart(fig1, use_container_width=True)

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
            figx.update_layout(title=f"{view_mode} – {c} vs LapDistPct", xaxis_title="LapDistPct", yaxis_title=c)
            st.plotly_chart(figx, use_container_width=True)

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
        figA.update_layout(title=f"{view_mode} – selected columns vs LapDistPct", xaxis_title="LapDistPct", yaxis_title="Value")
        st.plotly_chart(figA, use_container_width=True)
    st.dataframe(df.head(500), use_container_width=True)

with tab_flags:
    st.subheader("Flag problem spots (goes into export)")
    col1, col2, col3, col4 = st.columns([1,1,1,2])
    with col1:
        start_pct = st.number_input("Start %", min_value=0.0, max_value=1.0, value=0.10, step=0.005, format="%.3f")
    with col2:
        end_pct = st.number_input("End %", min_value=0.0, max_value=1.0, value=0.20, step=0.005, format="%.3f")
    with col3:
        flag_type = st.selectbox("Type", ["Loose on entry","Loose mid","Loose on exit","Tight on entry","Tight mid","Tight on exit","Other"])
    with col4:
        note = st.text_input("Quick note (optional)", value="")

    colA, colB = st.columns([1,1])
    with colA:
        if st.button("➕ Add Flag"):
            if end_pct <= start_pct:
                st.warning("End must be greater than Start.")
            else:
                st.session_state.user_flags.append({"start_pct": float(start_pct), "end_pct": float(end_pct), "type": flag_type, "note": note})
                st.success("Flag added.")
    with colB:
        if st.button("🧹 Clear All Flags"):
            st.session_state.user_flags = []
            st.info("Flags cleared.")

    if st.session_state.user_flags:
        st.write("Current flags:")
        st.dataframe(pd.DataFrame(st.session_state.user_flags))

    def simple_findings(df_all, segments):
        out = []
        for corner, (a,b) in segments.items():
            seg = df_all[(df_all["LapDistPct"] >= a) & (df_all["LapDistPct"] <= b)]
            if len(seg) < 10:
                out.append({"corner": corner, "issue": "—", "severity": ""}); continue
            throttle = seg["Throttle"].mean() if "Throttle" in seg else np.nan
            speed_drop = (seg["Speed"].max() - seg["Speed"].min()) if "Speed" in seg else np.nan
            issue, sev = "—", ""
            if pd.notna(throttle) and pd.notna(speed_drop):
                if throttle > 70 and speed_drop < 5: issue, sev = "Loose on exit", "slight"
                elif speed_drop > 10: issue, sev = "Tight on entry", "slight"
            out.append({"corner": corner, "issue": issue, "severity": sev})
        return pd.DataFrame(out)

    findings_df = simple_findings(df, segs)
    st.subheader("Corner findings (quick heuristic)")
    st.dataframe(findings_df, use_container_width=True)

    summary = {
        "car": "NASCAR Next Gen",
        "track": track,
        "session": {"type": run_type, "view": view_mode, "laps": int(df["Lap"].max() - df["Lap"].min() + 1) if len(laps) else 0},
        "conditions": {"track_temp_F": float(df.get("TrackTemp", pd.Series([np.nan])).iloc[0]) if "TrackTemp" in df.columns else None,
                       "baseline_temp_F": 85},
        "pressures_ending_psi": {k: float(df[k].iloc[-1]) for k in ["LFpressure","RFpressure","LRpressure","RRpressure"] if k in df.columns},
        "ride_heights_in": {k: float(df[k].median()) for k in ["CFSRrideHeight","LFrideHeight","RFrideHeight","LRrideHeight","RRrideHeight"] if k in df.columns},
        "corner_findings": findings_df.to_dict(orient="records"),
        "user_flags": st.session_state.user_flags,
    }

    export_text = build_chatgpt_export(summary)
    st.markdown("---")
    st.subheader("Copy for ChatGPT")
    st.download_button("Download export (.txt)", data=export_text.encode("utf-8"),
                       file_name="chatgpt_export.txt", mime="text/plain")
    st.text_area("Preview", export_text, height=260)
