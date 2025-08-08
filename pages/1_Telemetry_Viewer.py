import json
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import pathlib, tempfile, os

st.title("📊 Telemetry Viewer (CSV & IBT)")
st.caption("Upload a CSV or raw iRacing .ibt. If Lap/LapDistPct are missing in CSV, we'll synthesize them so charts still render.")

# ===== ChatGPT export header (we auto-fill the JSON below) =====
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

def build_chatgpt_export(summary_dict):
    def round_half(x): return round(float(x) * 2) / 2.0
    if "pressures_ending_psi" in summary_dict:
        for k, v in summary_dict["pressures_ending_psi"].items():
            summary_dict["pressures_ending_psi"][k] = round_half(v)
    json_block = json.dumps(summary_dict, indent=2)
    return CHATGPT_HEADER.replace("{{TELEMETRY_JSON_PASTE_HERE}}", json_block)

def coerce_min_columns(df: pd.DataFrame):
    """
    Make sure we have Lap, LapDistPct, Speed, Throttle, Brake.
    If Lap or LapDistPct are missing (CSV), synthesize so charts still render.
    """
    notes = []
    # Normalize throttle/brake to 0–100 if given 0–1
    for col in ("Throttle", "Brake"):
        if col in df.columns:
            try:
                if float(df[col].max()) <= 1.5:
                    df[col] = (df[col] * 100.0).clip(0, 100)
            except Exception:
                pass

    if "Lap" not in df.columns:
        df["Lap"] = 1  # single-lap fallback
        notes.append("Lap")

    if "LapDistPct" not in df.columns:
        if "LapDist" in df.columns and df["LapDist"].max() > 0:
            df["LapDistPct"] = df["LapDist"] / df.groupby("Lap")["LapDist"].transform("max").replace(0, 1)
        else:
            df["_idx"] = df.groupby("Lap").cumcount()
            max_idx = df.groupby("Lap")["_idx"].transform("max").replace(0, 1)
            df["LapDistPct"] = df["_idx"] / max_idx
            df.drop(columns=["_idx"], inplace=True)
        notes.append("LapDistPct")

    required = {"Speed", "Throttle", "Brake"}
    missing = sorted(list(required - set(df.columns)))
    if missing:
        return df, notes, missing
    return df, notes, []

# ===== IBT loader =====
def load_ibt_to_df(uploaded_file):
    """
    Load an iRacing .ibt file into a pandas DataFrame.
    Tries pyirsdk's IBT reader. If it's not available or fails, we raise so the UI can warn.
    """
    try:
        import irsdk  # provided by pyirsdk
    except Exception as e:
        st.error("pyirsdk isn't installed on this build. Add 'pyirsdk' and 'PyYAML' to requirements.txt.")
        raise

    # save to a temp path first
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ibt") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    try:
        # Try common IBT reader patterns
        ibt = None
        if hasattr(irsdk, "IBT"):
            ibt = irsdk.IBT(tmp_path)
        elif hasattr(irsdk, "ibt"):
            ibt = irsdk.ibt.IBT(tmp_path)
        if ibt is None:
            raise RuntimeError("pyirsdk.IBT class not found")

        # some versions need explicit open()
        try:
            if hasattr(ibt, "open"):
                ibt.open()
        except Exception:
            pass

        # channels we care about
        want = ["Lap", "LapDistPct", "LapDist", "Speed", "Throttle", "Brake",
                "SteeringWheelAngle", "YawRate", "RRshockVel", "CFSRrideHeight",
                "LFpressure","RFpressure","LRpressure","RRpressure",
                "LFrideHeight","RFrideHeight","LRrideHeight","RRrideHeight"]

        data = {}
        for ch in want:
            arr = None
            for getter in ("get", "get_channel", "get_channel_data_by_name"):
                try:
                    fn = getattr(ibt, getter)
                    maybe = fn(ch)
                    if maybe is not None:
                        arr = maybe
                        break
                except Exception:
                    continue
            if arr is not None:
                data[ch] = arr

        if not data:
            raise RuntimeError("No known channels found in IBT.")

        df = pd.DataFrame(data).dropna(how="all")

        # Normalize throttle/brake to 0–100 if 0–1
        for col in ("Throttle","Brake"):
            if col in df.columns and df[col].max() <= 1.5:
                df[col] = (df[col] * 100.0).clip(0,100)

        # Build LapDistPct if missing
        if "LapDistPct" not in df.columns:
            if "LapDist" in df.columns and df["LapDist"].max() > 0:
                df["Lap"] = df["Lap"].fillna(method="ffill").fillna(1).astype(int) if "Lap" in df.columns else 1
                df["LapDistPct"] = df["LapDist"] / df.groupby("Lap")["LapDist"].transform("max").replace(0, 1)
            else:
                df["_idx"] = df.groupby("Lap").cumcount() if "Lap" in df.columns else np.arange(len(df))
                max_idx = df.groupby("Lap")["_idx"].transform("max").replace(0, 1) if "Lap" in df.columns else max(1, len(df)-1)
                if isinstance(max_idx, pd.Series):
                    df["LapDistPct"] = df["_idx"] / max_idx
                else:
                    df["LapDistPct"] = df["_idx"] / float(max_idx)
                if "_idx" in df.columns: df.drop(columns=["_idx"], inplace=True)

        # Stash session YAML if available
        try:
            if hasattr(ibt, "get_session_info"):
                st.session_state["_session_yaml"] = ibt.get_session_info()
        except Exception:
            pass

        return df
    finally:
        try:
            if 'ibt' in locals() and hasattr(ibt, "close"):
                ibt.close()
        except Exception:
            pass
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

with st.sidebar:
    up = st.file_uploader("Upload telemetry (.csv or .ibt)", type=["csv","ibt"])
    track = st.selectbox("Track", ["Watkins Glen International"], index=0)

    segs = DEFAULT_WGI_SEGMENTS.copy()
    with st.expander("Adjust corner ranges (LapDistPct)"):
        for k in list(segs.keys()):
            a, b = segs[k]
            a2 = st.slider(f"{k} start", 0.0, 1.0, float(a), 0.005, key=f"{k}_a")
            b2 = st.slider(f"{k} end",   0.0, 1.0, float(b), 0.005, key=f"{k}_b")
            if b2 < a2: b2 = a2 + 0.01
            segs[k] = [a2, b2]

    run_type = st.radio("Run type", ["Qualifying","Short Run","Long Run"], index=1)

if not up:
    st.info("Upload a CSV or IBT with at least Speed, Throttle, and Brake. (Lap/LapDistPct optional; we'll synthesize if missing)")
    st.stop()

# ===== Load file (CSV or IBT) =====
suffix = pathlib.Path(up.name).suffix.lower()
if suffix == ".csv":
    try:
        df = pd.read_csv(up)
    except Exception as e:
        st.error(f"Error reading CSV: {e}")
        st.stop()
    df, synthesized, missing_core = coerce_min_columns(df)
    if synthesized:
        st.warning(f"Synthesized columns for charts: {', '.join(synthesized)}")
    if missing_core:
        st.error(f"Missing core columns for charts: {', '.join(missing_core)}")
        st.stop()
elif suffix == ".ibt":
    try:
        df = load_ibt_to_df(up)
    except Exception as e:
        st.error(f"Failed to parse IBT: {e}")
        st.stop()
else:
    st.error("Unsupported file type.")
    st.stop()

# ===== Lap select =====
if "Lap" not in df.columns:
    df["Lap"] = 1
laps = sorted(pd.unique(df["Lap"]).tolist())
sel_lap = st.selectbox("Select lap", laps, index=0)
lap_df = df[df["Lap"] == sel_lap].copy()

# ===== Chart 1: Speed vs distance =====
fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=lap_df["LapDistPct"], y=lap_df["Speed"], mode="lines", name="Speed (mph)"))
shaded_corners(fig1, segs)
fig1.update_layout(title=f"Lap {sel_lap} – Speed vs Lap Distance", xaxis_title="LapDistPct", yaxis_title="Speed (mph)")
st.plotly_chart(fig1, use_container_width=True)

# ===== Chart 2: Throttle / Brake =====
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=lap_df["LapDistPct"], y=lap_df["Throttle"], mode="lines", name="Throttle %"))
fig2.add_trace(go.Scatter(x=lap_df["LapDistPct"], y=lap_df["Brake"], mode="lines", name="Brake %"))
shaded_corners(fig2, segs)
fig2.update_layout(title=f"Lap {sel_lap} – Throttle & Brake", xaxis_title="LapDistPct", yaxis_title="%")
st.plotly_chart(fig2, use_container_width=True)

# ===== Optional charts if columns exist =====
if "RRshockVel" in lap_df.columns:
    rows = []
    for k, (a, b) in segs.items():
        seg = lap_df[(lap_df["LapDistPct"] >= a) & (lap_df["LapDistPct"] <= b)]
        if len(seg):
            rows.append({"corner": k, "data": seg["RRshockVel"].values})
    if rows:
        fig3 = go.Figure()
        for r in rows:
            fig3.add_trace(go.Box(y=r["data"], name=r["corner"]))
        fig3.update_layout(title="RR Shock Velocity by Corner (per-lap)", yaxis_title="in/s")
        st.plotly_chart(fig3, use_container_width=True)

if "CFSRrideHeight" in lap_df.columns:
    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(x=lap_df["Speed"], y=lap_df["CFSRrideHeight"], mode="markers", name="CFSR Ride Height"))
    fig4.update_layout(title="Splitter / Center Ride Height vs Speed", xaxis_title="Speed (mph)", yaxis_title="Height (in)")
    st.plotly_chart(fig4, use_container_width=True)

# ===== Simple corner findings (placeholder logic) =====
def simple_findings(df_all, segments, lap):
    out = []
    lap_df = df_all[df_all["Lap"] == lap]
    for corner, (a, b) in segments.items():
        seg = lap_df[(lap_df["LapDistPct"] >= a) & (lap_df["LapDistPct"] <= b)]
        if len(seg) < 5:
            out.append({"corner": corner, "issue": "—", "severity": ""})
            continue
        throttle = seg["Throttle"].mean() if "Throttle" in seg else np.nan
        speed_drop = (seg["Speed"].max() - seg["Speed"].min()) if "Speed" in seg else np.nan
        issue, sev = "—", ""
        if pd.notna(throttle) and pd.notna(speed_drop):
            if throttle > 70 and speed_drop < 5:
                issue, sev = "Loose on exit", "slight"
            elif speed_drop > 10:
                issue, sev = "Tight on entry", "slight"
        out.append({"corner": corner, "issue": issue, "severity": sev})
    return pd.DataFrame(out)

findings_df = simple_findings(df, segs, sel_lap)
st.subheader("Corner findings")
st.dataframe(findings_df, use_container_width=True)

# ===== Build export summary =====
summary = {
    "car": "NASCAR Next Gen",
    "track": track,
    "session": {"type": run_type, "laps": int(df["Lap"].max() - df["Lap"].min() + 1) if len(laps) else 0},
    "conditions": {
        "track_temp_F": float(df.get("TrackTemp", pd.Series([np.nan])).iloc[0]) if "TrackTemp" in df.columns else None,
        "baseline_temp_F": 85
    },
    "pressures_ending_psi": {k: float(df[k].iloc[-1]) for k in ["LFpressure","RFpressure","LRpressure","RRpressure"] if k in df.columns},
    "ride_heights_in": {k: float(df[k].median()) for k in ["CFSRrideHeight","LFrideHeight","RFrideHeight","LRrideHeight","RRrideHeight"] if k in df.columns},
    "corner_findings": findings_df.to_dict(orient="records"),
    "suggestions": []
}

# ===== Export block =====
export_text = build_chatgpt_export(summary)

st.markdown("---")
st.subheader("Copy for ChatGPT")
st.download_button("Download export (.txt)", data=export_text.encode("utf-8"),
                   file_name="chatgpt_export.txt", mime="text/plain")
st.text_area("Preview", export_text, height=280)
