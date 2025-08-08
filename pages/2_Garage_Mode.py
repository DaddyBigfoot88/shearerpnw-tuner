
import pathlib, tempfile, json, math
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(layout="wide")
st.title("🧰 Garage Mode (Lap Compare)")
st.caption("Overlay laps, time delta, stacked channels, sector splits, and click-to-note.")

# ---------- Helpers ----------
def ensure_min_columns(df: pd.DataFrame):
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
    return df, notes

def get_time_column(df):
    for c in ["SessionTime","LapCurrentLapTime","Time","Timestamp","sessionTime"]:
        if c in df.columns:
            try:
                return pd.to_numeric(df[c], errors="coerce").fillna(method="ffill").values
            except Exception:
                continue
    # best effort: assume ~60Hz if nothing present
    idx = np.arange(len(df))
    return (idx / 60.0).astype(float)

def lap_series(df, lap_id, xcol="LapDistPct", tcol="__time__"):
    d = df[df["Lap"] == lap_id]
    x = pd.to_numeric(d[xcol], errors="coerce").values
    t = pd.to_numeric(d[tcol], errors="coerce").values
    return x, t, d

def interp_time_at_pct(x, t, pcts=np.linspace(0,1,500)):
    if len(x) < 2: 
        return pcts, np.full_like(pcts, np.nan)
    order = np.argsort(x)
    x_sorted, t_sorted = x[order], t[order]
    # drop dup x to avoid interpolation issues
    mask = np.diff(np.r_[[-1], x_sorted]) != 0
    xu, tu = x_sorted[mask], t_sorted[mask]
    tu0 = tu - float(tu.min())
    tt = np.interp(pcts, np.clip(xu, 0, 1), tu0, left=np.nan, right=np.nan)
    return pcts, tt

DEFAULT_WGI_SEGMENTS = {
    "S1": [0.00, 0.20],
    "S2": [0.20, 0.40],
    "S3": [0.40, 0.60],
    "S4": [0.60, 0.80],
    "S5": [0.80, 1.00]
}

def sector_times(pcts, tcurve):
    out = {}
    for name,(a,b) in DEFAULT_WGI_SEGMENTS.items():
        # duration inside sector
        i0 = np.nanargmin(np.abs(pcts - a))
        i1 = np.nanargmin(np.abs(pcts - b))
        if i1 <= i0: i1 = i0+1
        out[name] = float(tcurve[i1] - tcurve[i0])
    return out

# ---------- Sidebar ----------
with st.sidebar:
    up = st.file_uploader("Upload telemetry (.csv)", type=["csv"])
    st.caption("IBT-to-CSV: use the Telemetry Viewer page to export a CSV if you need to.")
    show_all = st.checkbox("Show ALL numeric sensors", value=False,
        help="If OFF, we'll show common channels first. If ON, everything numeric is selectable.")
    channel_filter = st.text_input("Filter channels (contains)", "")
    colorA = "#d62728"; colorB = "#1f77b4"

if not up:
    st.info("Upload a CSV exported from your run. Needs at least Lap, LapDistPct (we'll synthesize), and a few sensors.")
    st.stop()

df = pd.read_csv(up)
df, synth = ensure_min_columns(df)
if synth: st.warning("Synthesized: " + ", ".join(synth))
df["__time__"] = get_time_column(df)

laps = sorted(pd.unique(df["Lap"]).tolist())
if len(laps) < 1:
    st.error("No laps found."); st.stop()

col_a, col_b, col_c = st.columns([1,1,2])
with col_a:
    lapA = st.selectbox("Lap A", laps, index=0)
with col_b:
    lapB = st.selectbox("Lap B", laps, index=min(1,len(laps)-1))
with col_c:
    x_mode = st.radio("X-axis", ["LapDistPct","Time"], horizontal=True)

# ---------- Build data for A/B ----------
xA, tA, dA = lap_series(df, lapA)
xB, tB, dB = lap_series(df, lapB)

# Time delta vs distance (align by pct)
pcts = np.linspace(0, 1, 600)
pA, tcurveA = interp_time_at_pct(xA, tA, pcts=pcts)
pB, tcurveB = interp_time_at_pct(xB, tB, pcts=pcts)
delta = tcurveB - tcurveA  # positive = lap B slower

# Sector table
sA = sector_times(pA, tcurveA)
sB = sector_times(pB, tcurveB)
sec_df = pd.DataFrame({
    "Sector": list(DEFAULT_WGI_SEGMENTS.keys()),
    "Lap A (s)": [round(sA[k],3) for k in DEFAULT_WGI_SEGMENTS.keys()],
    "Lap B (s)": [round(sB[k],3) for k in DEFAULT_WGI_SEGMENTS.keys()],
    "Δ (B - A) s": [round(sB[k]-sA[k],3) for k in DEFAULT_WGI_SEGMENTS.keys()]
})

# ---------- Left: map placeholder + delta ----------
left, right = st.columns([1.2, 2.0])

with left:
    st.subheader("Time delta vs distance")
    fig_delta = go.Figure()
    fig_delta.add_trace(go.Scatter(x=pA, y=delta, mode="lines", name="Δt (B - A)"))
    fig_delta.update_layout(xaxis_title="LapDistPct", yaxis_title="seconds (B-A)", height=260)
    st.plotly_chart(fig_delta, use_container_width=True)
    st.subheader("Sector splits")
    st.dataframe(sec_df, use_container_width=True, height=240)

# ---------- Right: stacked channels (overlay A/B) ----------
common = ["Speed","Throttle","Brake","SteeringWheelAngle","YawRate","Gear"]
if show_all:
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and c not in ["Lap","LapDistPct","__time__"]]
else:
    numeric_cols = [c for c in common if c in df.columns]

if channel_filter:
    numeric_cols = [c for c in numeric_cols if channel_filter.lower() in c.lower()]

select_cols = st.multiselect("Channels to plot (overlay A/B)", numeric_cols, default=numeric_cols[:4])

if "notes" not in st.session_state: st.session_state.notes = []

if select_cols:
    rows = len(select_cols)
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.02,
                        subplot_titles=select_cols)
    for i, col in enumerate(select_cols, start=1):
        xA_plot = dA["LapDistPct"] if x_mode == "LapDistPct" else dA["__time__"]
        xB_plot = dB["LapDistPct"] if x_mode == "LapDistPct" else dB["__time__"]
        fig.add_trace(go.Scatter(x=xA_plot, y=dA[col], mode="lines", name=f"{col} — Lap A", line=dict(color=colorA)), row=i, col=1)
        fig.add_trace(go.Scatter(x=xB_plot, y=dB[col], mode="lines", name=f"{col} — Lap B", line=dict(color=colorB)), row=i, col=1)
    fig.update_layout(height=250*rows, legend=dict(orientation="h"), margin=dict(t=30))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Pick at least one channel to graph.")

# ---------- Notes panel (click to add) ----------
st.markdown("---")
st.subheader("Notes")
st.caption("Click any graph to add a note at that X (LapDistPct or Time).")

leftN, rightN = st.columns([2,1])
with leftN:
    st.dataframe(pd.DataFrame(st.session_state.notes) if st.session_state.notes else pd.DataFrame([{"tip":"No notes yet"}]), use_container_width=True, height=240)
with rightN:
    # Capture a click anywhere in the last plot / delta plot
    try:
        from streamlit_plotly_events import plotly_events
        st.caption("Click the Δt chart to place a note:")
        clicks = plotly_events(fig_delta, click_event=True, select_event=False, hover_event=False, key="delta_clicks")
        if clicks:
            xval = clicks[-1].get("x", None)
            if xval is not None:
                text = st.text_input("Note text", key="note_text", value="")
                if st.button("Add note here"):
                    st.session_state.notes.append({"x": float(xval), "x_mode": "LapDistPct", "text": text})
                    st.success("Note added.")
    except Exception as e:
        st.info("Install 'streamlit-plotly-events' to enable click-to-note.")
        st.code("pip install streamlit-plotly-events")

# ---------- Export ----------
st.markdown("---")
st.subheader("Export lap compare + notes (JSON)")
export_payload = {
    "lapA": int(lapA),
    "lapB": int(lapB),
    "x_mode": x_mode,
    "sectors": DEFAULT_WGI_SEGMENTS,
    "sector_times": {"A": sA, "B": sB},
    "delta_curve": {"pct": pA.tolist(), "delta_s": delta.tolist()},
    "notes": st.session_state.notes,
    "channels": select_cols
}
st.download_button("Download garage_compare.json", data=json.dumps(export_payload, indent=2).encode("utf-8"),
                   file_name="garage_compare.json", mime="application/json")
