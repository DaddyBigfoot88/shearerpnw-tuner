import io, json, math
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Easy Tuner – Telemetry", layout="wide")

# -----------------------------
# Defaults you can edit later
# -----------------------------
DEFAULT_SEVERITY_MAP = {
  "limits": {
    "shock_clicks_min": 0, "shock_clicks_max": 10,
    "diff_preload_min_ftlbs": 0, "diff_preload_max_ftlbs": 75,
    "lf_caster_min_deg": 8.0, "tire_pressure_step_psi": 0.5
  },
  "severity_to_changes": {
    "tire_pressure_psi": { "slight": 0.5, "moderate": 1.0, "severe": 1.5 },
    "shock_clicks": { "slight": 1, "moderate": 2, "severe": 3 },
    "crossweight_percent": { "slight": 0.3, "moderate": 0.5, "severe": 0.8 },
    "ride_height_in": { "slight": 0.05, "moderate": 0.10, "severe": 0.15 }
  }
}

# Rough lap-distance (0–1) segments for Watkins Glen (you can tweak in UI)
DEFAULT_WGI_SEGMENTS = {
  "T1":  [0.02, 0.10],
  "T2":  [0.18, 0.24],
  "T3":  [0.24, 0.28],
  "Bus Stop": [0.43, 0.52],
  "T5":  [0.55, 0.63],
  "T6":  [0.75, 0.83],
  "T7":  [0.88, 0.97]
}

CHATGPT_HEADER = """(Just paste everything below into ChatGPT and hit Enter.)

=== CHATGPT SETUP COACH INSTRUCTIONS (PASTE THIS WHOLE BLOCK) ===
You are a NASCAR Next Gen setup coach. Analyze the telemetry summary and give setup changes.

Rules you must follow:
- Use exact, garage-style outputs grouped by Tires, Chassis, Suspension, Rear End.
- Shocks: 0–10 clicks only. Tire pressures: change in 0.5 psi steps. Diff preload: 0–75 ft-lbs. LF caster ≥ +8.0°.
- If a suggested change conflicts with limits, cap it and say so.
- If track temp is lower than baseline, bias pressures down per 0.5 psi per ~10–15°F; higher temps bias up. Then fine-tune by tire edge temps.
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

End of data. Now give setup changes.
=== END INSTRUCTIONS ===
"""

# -----------------------------
# Helpers
# -----------------------------
@st.cache_data(show_spinner=False)
def load_severity_map():
    try:
        return json.load(open("rules/severity_map.json", "r"))
    except Exception:
        return DEFAULT_SEVERITY_MAP

def round_to_half(x):
    return round(x * 2) / 2.0

def build_chatgpt_export(summary_dict, header_text=CHATGPT_HEADER):
    # Round pressures if present
    if "pressures_ending_psi" in summary_dict:
        for k, v in summary_dict["pressures_ending_psi"].items():
            summary_dict["pressures_ending_psi"][k] = round_to_half(float(v))
    return header_text.replace("{{TELEMETRY_JSON_PASTE_HERE}}",
                               json.dumps(summary_dict, indent=2))

def shaded_corners(fig, segments, y0, y1, name="corner"):
    for label, (x0, x1) in segments.items():
        fig.add_vrect(x0=x0, x1=x1, fillcolor=None, line_width=0,
                      annotation_text=label, annotation_position="top left",
                      opacity=0.08)

# -----------------------------
# IBT/CSV readers
# -----------------------------
def read_csv_to_df(f) -> pd.DataFrame:
    df = pd.read_csv(f)
    # Expect columns like: Time, Lap, LapDistPct, Speed, Throttle, Brake, SteeringWheelAngle, YawRate,
    # LFshockVel, RFshockVel, LRshockVel, RRshockVel, CFSRrideHeight, LFtempI/M/O, etc.
    # Make sure key columns exist
    needed = ["Time", "Lap", "LapDistPct", "Speed", "Throttle", "Brake"]
    for col in needed:
        if col not in df.columns:
            raise ValueError(f"CSV missing required column: {col}")
    return df

def read_ibt_to_df(uploaded_file) -> pd.DataFrame:
    """
    Plug your real IBT parser here.
    If you already built telemetry/ibt_parser.py, import and call it.
    Otherwise, install a parser library you like and return a tidy DataFrame
    with at least: Time, Lap, LapDistPct, Speed, Throttle, Brake, SteeringWheelAngle,
    YawRate, LFshockVel, RFshockVel, LRshockVel, RRshockVel, CFSRrideHeight.
    """
    try:
        # Example if you wrote your own module:
        # from telemetry.ibt_parser import read_ibt
        # return read_ibt(uploaded_file)
        raise NotImplementedError("Hook up your IBT parser here.")
    except Exception as e:
        raise RuntimeError(
            "IBT parsing not wired yet. Add your parser (telemetry/ibt_parser.py) "
            "or upload a CSV export for now. Error: {}".format(e)
        )

def load_uploaded(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return read_csv_to_df(uploaded_file)
    if name.endswith(".ibt"):
        return read_ibt_to_df(uploaded_file)
    raise ValueError("Please upload a .ibt or .csv file")

# -----------------------------
# Simple analyzers (heuristics)
# -----------------------------
def flag_loose_exit(df_seg):
    # throttle high, steering unwinding, yaw spike while latG-ish (use Speed curvature proxy)
    thr = np.nanmean(df_seg["Throttle"])
    yaw_pk = np.nanmax(np.abs(df_seg.get("YawRate", pd.Series([0]))))
    steer = df_seg.get("SteeringWheelAngle", pd.Series([0]))
    # crude unwind proxy: first minus last
    unwind = (steer.iloc[0] - steer.iloc[-1]) if len(steer) > 2 else 0
    rr_sv = np.nanmax(np.abs(df_seg.get("RRshockVel", pd.Series([0]))))
    score = 0
    score += 0.25 if thr > 70 else 0
    score += 0.35 if yaw_pk > 1.0 else 0
    score += 0.25 if rr_sv > 10.0 else 0
    score += 0.15 if unwind > 50 else 0
    if score >= 0.75: return "severe"
    if score >= 0.5:  return "moderate"
    if score >= 0.3:  return "slight"
    return ""

def flag_tight_entry(df_seg):
    steer = np.nanmedian(np.abs(df_seg.get("SteeringWheelAngle", pd.Series([0]))))
    speed_drop = np.nanmax(df_seg["Speed"]) - np.nanmin(df_seg["Speed"])
    front_rh_up = np.nanmax(df_seg.get("LFrideHeight", pd.Series([0]))) - np.nanmin(df_seg.get("LFrideHeight", pd.Series([0])))
    score = 0
    score += 0.4 if steer > 120 else 0
    score += 0.35 if speed_drop > 3 else 0
    score += 0.25 if front_rh_up > 0.05 else 0
    if score >= 0.75: return "severe"
    if score >= 0.5:  return "moderate"
    if score >= 0.3:  return "slight"
    return ""

def summarize_corner_findings(df, segments, lap):
    out = []
    lap_df = df[df["Lap"] == lap]
    for corner, (a, b) in segments.items():
        seg = lap_df[(lap_df["LapDistPct"] >= a) & (lap_df["LapDistPct"] <= b)]
        if len(seg) < 5: 
            out.append({"corner": corner, "issue": "—", "severity": ""})
            continue
        loose = flag_loose_exit(seg)
        tight = flag_tight_entry(seg)
        issue = "—"; sev = ""
        if loose:
            issue, sev = "Loose on exit", loose
        elif tight:
            issue, sev = "Tight on entry", tight
        out.append({"corner": corner, "issue": issue, "severity": sev})
    return pd.DataFrame(out)

# -----------------------------
# UI
# -----------------------------
st.title("Easy Tuner – Telemetry Viewer (IBT/CSV)")

with st.sidebar:
    st.markdown("### Upload your file")
    up = st.file_uploader("Drop .ibt or .csv", type=["ibt","csv"])
    st.markdown("---")
    st.markdown("### Track & segments")
    track = st.selectbox("Track", ["Watkins Glen International"], index=0)
    segs = DEFAULT_WGI_SEGMENTS.copy()
    with st.expander("Adjust corner ranges (LapDistPct)"):
        for k in list(segs.keys()):
            a,b = segs[k]
            a2 = st.slider(f"{k} start", 0.0, 1.0, float(a), 0.005, key=f"{k}_a")
            b2 = st.slider(f"{k} end",   0.0, 1.0, float(b), 0.005, key=f"{k}_b")
            if b2 < a2: b2 = a2 + 0.01
            segs[k] = [a2, b2]
    st.markdown("---")
    run_type = st.radio("Run type", ["Qualifying","Short Run","Long Run"], index=1)
    st.caption("PS: You can save these as defaults later.")

if not up:
    st.info("Upload an **.ibt** (or a **.csv export**) to see charts.")
    st.stop()

# Load data
try:
    df = load_uploaded(up)
except Exception as e:
    st.error(str(e))
    st.stop()

# Basic cleanups
for col in ["Time","Lap","LapDistPct","Speed","Throttle","Brake"]:
    if col not in df.columns:
        st.error(f"Missing required column: {col}")
        st.stop()

# Lap selection
laps = sorted(df["Lap"].dropna().unique().tolist())
sel_lap = st.selectbox("Select lap", laps, index=min(1, len(laps)-1))  # pick a mid/better lap
lap_df = df[df["Lap"] == sel_lap].copy()

# -----------------------------
# CHART 1: Speed trace with corners
# -----------------------------
c1 = go.Figure()
c1.add_trace(go.Scatter(x=lap_df["LapDistPct"], y=lap_df["Speed"], mode="lines", name="Speed (mph)"))
shaded_corners(c1, segs, y0=0, y1=lap_df["Speed"].max())
c1.update_layout(title=f"Lap {sel_lap} – Speed vs Lap Distance", xaxis_title="LapDistPct (0–1)", yaxis_title="Speed (mph)")
st.plotly_chart(c1, use_container_width=True)

# -----------------------------
# CHART 2: Throttle / Brake vs distance
# -----------------------------
c2 = go.Figure()
c2.add_trace(go.Scatter(x=lap_df["LapDistPct"], y=lap_df["Throttle"], mode="lines", name="Throttle %"))
c2.add_trace(go.Scatter(x=lap_df["LapDistPct"], y=lap_df["Brake"], mode="lines", name="Brake %"))
shaded_corners(c2, segs, y0=0, y1=100)
c2.update_layout(title=f"Lap {sel_lap} – Throttle/Brake", xaxis_title="LapDistPct (0–1)", yaxis_title="%")
st.plotly_chart(c2, use_container_width=True)

# -----------------------------
# CHART 3: Shock velocity box plot per corner (RR as example)
# -----------------------------
rows = []
for k,(a,b) in segs.items():
    seg = lap_df[(lap_df["LapDistPct"]>=a) & (lap_df["LapDistPct"]<=b)]
    if "RRshockVel" in seg.columns and len(seg):
        rows.append({"corner":k, "RRshockVel":seg["RRshockVel"].values})
if rows:
    c3 = go.Figure()
    for r in rows:
        c3.add_trace(go.Box(y=r["RRshockVel"], name=r["corner"]))
    c3.update_layout(title="RR Shock Velocity by Corner (per-lap boxes)", yaxis_title="in/s")
    st.plotly_chart(c3, use_container_width=True)
else:
    st.warning("No RRshockVel column found. Add shock velocity channels to CSV/IBT parser.")

# -----------------------------
# CHART 4: Ride height vs speed scatter
# -----------------------------
if "CFSRrideHeight" in lap_df.columns:
    c4 = go.Figure()
    c4.add_trace(go.Scatter(x=lap_df["Speed"], y=lap_df["CFSRrideHeight"], mode="markers", name="CFSRrideHeight"))
    c4.update_layout(title=f"Splitter/Center Ride Height vs Speed", xaxis_title="Speed (mph)", yaxis_title="Height (in)")
    st.plotly_chart(c4, use_container_width=True)

# -----------------------------
# TABLE/HEAT: Findings by corner
# -----------------------------
findings_df = summarize_corner_findings(df, segs, sel_lap)
st.subheader("Corner findings")
st.dataframe(findings_df, use_container_width=True)

# -----------------------------
# EXPORT: Build ChatGPT-ready block
# -----------------------------
st.markdown("---")
st.subheader("Copy for ChatGPT")

# Build a compact summary JSON for export
summary = {
    "car": "NASCAR Next Gen",
    "track": track,
    "session": {"type": run_type, "laps": int(df['Lap'].max() - df['Lap'].min() + 1) if len(laps) else 0},
    "conditions": {
        # Fill these from IBT if present:
        "track_temp_F": float(df.get("TrackTemp", pd.Series([np.nan])).iloc[0]) if "TrackTemp" in df.columns else None,
        "baseline_temp_F": 85  # put your baseline here or pull from rules
    },
    "pressures_ending_psi": {
        k: float(df[k].iloc[-1]) for k in ["LFpressure","RFpressure","LRpressure","RRpressure"] if k in df.columns
    },
    "ride_heights_in": {
        k: float(df[k].median()) for k in ["CFSRrideHeight","LFrideHeight","RFrideHeight","LRrideHeight","RRrideHeight"] if k in df.columns
    },
    "corner_findings": findings_df.to_dict(orient="records"),
    "suggestions": []  # you can fill with your rule_engine outputs here
}

export_text = build_chatgpt_export(summary)
st.download_button("Download export (.txt)", data=export_text.encode("utf-8"),
                   file_name="chatgpt_export.txt", mime="text/plain")
st.text_area("Preview", export_text, height=240)
