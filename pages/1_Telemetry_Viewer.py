
import io, json, os, pathlib, tempfile, math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(layout="wide")
st.title("📊 Telemetry Viewer — Simple (CSV or IBT)")
st.caption("Upload your data, (optional) quick graphs, mark corner feelings, then export a ChatGPT-ready block with hard setup rules.")

# ===== Helpers =====
def coerce_min_columns(df: pd.DataFrame):
    notes = []
    # Throttle/Brake normalize to 0-100 if 0-1
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
            # Per-lap normalization
            df["LapDistPct"] = df["LapDist"] / df.groupby("Lap")["LapDist"].transform("max").replace(0,1)
        else:
            df["_idx"] = df.groupby("Lap").cumcount()
            max_idx = df.groupby("Lap")["_idx"].transform("max").replace(0,1)
            df["LapDistPct"] = df["_idx"] / max_idx
            df.drop(columns=["_idx"], inplace=True)
        notes.append("LapDistPct")

    required = {"Speed","Throttle","Brake"}
    missing = sorted(list(required - set(df.columns)))
    return df, notes, missing

def load_ibt_to_df(uploaded_file):
    """Very simple IBT loader using pyirsdk if present."""
    try:
        import irsdk
    except Exception:
        st.error("pyirsdk isn't installed in this build. Add 'pyirsdk' and 'PyYAML' to requirements.txt.")
        raise

    with tempfile.NamedTemporaryFile(delete=False, suffix=".ibt") as tmp:
        tmp.write(uploaded_file.read()); tmp_path = tmp.name
    try:
        # Support both namespaces some wheels expose
        ibt = None
        if hasattr(irsdk, "IBT"): ibt = irsdk.IBT(tmp_path)
        elif hasattr(irsdk, "ibt"): ibt = irsdk.ibt.IBT(tmp_path)
        if ibt is None: raise RuntimeError("pyirsdk.IBT class not found")
        try:
            if hasattr(ibt, "open"): ibt.open()
        except Exception:
            pass

        want = ["Lap","LapDistPct","LapDist","Speed","Throttle","Brake"]
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

        # Normalize throttle/brake if needed
        for col in ("Throttle","Brake"):
            if col in df.columns and df[col].max() <= 1.5:
                df[col] = (df[col] * 100.0).clip(0,100)

        # Make LapDistPct if missing
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

DEFAULT_CORNERS = ["T1","T2","T3","T4","T5","T6","T7","T8","T9","T10","T11"]
FEELINGS = [
    "No issue / skip",
    "Loose on entry","Loose mid-corner","Loose on exit",
    "Tight on entry","Tight mid-corner","Tight on exit",
    "Understeer everywhere","Oversteer everywhere",
    "Porpoising / Bottoming","Brakes locking","Traction wheelspin","Other"]

# ===== Sidebar: Upload & options =====
with st.sidebar:
    up = st.file_uploader("Upload telemetry (.csv or .ibt)", type=["csv","ibt"])    
    show_charts = st.checkbox("Show quick graphs", value=False)
    track_name = st.selectbox("Track", ["Watkins Glen International"], index=0)
    run_type = st.radio("Run type", ["Practice","Qualifying","Race"], index=0, horizontal=True)
    baseline_temp = st.number_input("Baseline setup temp (°F)", 50, 140, 85)
    current_temp = st.number_input("Current track temp (°F)", 50, 140, 90)

# ===== Load file (optional) =====
df = None
if up is not None:
    suffix = pathlib.Path(up.name).suffix.lower()
    if suffix == ".csv":
        try:
            df = pd.read_csv(up)
        except Exception as e:
            st.error(f"CSV read error: {e}")
    elif suffix == ".ibt":
        try:
            df = load_ibt_to_df(up)
        except Exception as e:
            st.error(f"IBT parse error: {e}")
    if df is not None:
        df, synthesized, missing_core = coerce_min_columns(df)
        if synthesized:
            st.warning("Synthesized columns: " + ", ".join(synthesized))
        if missing_core:
            st.warning("CSV missing required columns: " + ", ".join(missing_core) + ". We'll still show what we can.")

# ===== Quick charts (optional) =====
if show_charts and df is not None:
    st.subheader("Quick graphs (Speed / Throttle / Brake)")
    laps = sorted(pd.unique(df["Lap"]).tolist()) if "Lap" in df.columns else [1]
    view_mode = st.radio("View", ["Per lap","Whole run"], index=0, horizontal=True)
    if view_mode == "Per lap":
        sel = st.selectbox("Lap", laps, index=0)
        plot_df = df[df["Lap"] == sel]
    else:
        plot_df = df.copy()
    fig = go.Figure()
    for col, name in [("Speed","Speed (mph)"),("Throttle","Throttle %"),("Brake","Brake %")]:
        if col in plot_df.columns:
            fig.add_trace(go.Scatter(x=plot_df["LapDistPct"], y=plot_df[col], mode="lines", name=name))
    fig.update_layout(xaxis_title="LapDistPct", yaxis_title="Value")
    st.plotly_chart(fig, use_container_width=True)

# ===== Corner Feedback (simple) =====
st.markdown("---")
st.header("🧭 Corner Feedback (simple)")
if "driver_feedback" not in st.session_state:
    st.session_state.driver_feedback = {c: {"feels":"No issue / skip","severity":0,"note":""} for c in DEFAULT_CORNERS}

cols = st.columns(3)
for i, c in enumerate(DEFAULT_CORNERS):
    with cols[i % 3]:
        st.markdown(f"**{c}**")
        feels = st.selectbox(f"{c} feel", FEELINGS, index=0, key=f"feel_{c}")
        severity = st.slider(f"{c} severity", 0, 10, st.session_state.driver_feedback[c].get("severity",0), key=f"sev_{c}")
        note = st.text_input(f"{c} note (optional)", value=st.session_state.driver_feedback[c].get("note",""), key=f"note_{c}")
        st.session_state.driver_feedback[c] = {"feels": feels, "severity": int(severity), "note": note}

st.success("Feedback saved in session.")

# ===== ChatGPT export with hard rules (opt-in) =====
st.markdown("---")
st.header("📤 Export to ChatGPT (with rules, no auto suggestions)")
generate_suggestions = st.checkbox("✅ Allow setup suggestions (opt-in)", value=False)
is_problem = st.checkbox("This run has real problems", value=False)

# Load setup rules JSON
rules_path = pathlib.Path("ShearerPNW_Easy_Tuner_Editables/setup_rules_nextgen.json")
if not rules_path.exists():
    st.error("Missing setup_rules_nextgen.json in ShearerPNW_Easy_Tuner_Editables/" )
else:
    setup_rules = json.loads(rules_path.read_text())

    CHATGPT_HEADER = """(Paste this whole block into ChatGPT and press Enter.)

=== CHATGPT SETUP COACH (CORNER FEEDBACK) ===
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
temps: {{"baseline_F": {{BASELINE}}, "current_F": {{CURRENT}}}}

OK—here is the data:

corner_feedback_json = 
```
{{CORNER_FEEDBACK_JSON}}
```

setup_rules = 
```
{{SETUP_RULES_JSON}}
```

gates = {"generate_suggestions": {{GATE_GEN}}, "is_problem": {{GATE_PROB}}}

End of data.
=== END INSTRUCTIONS ===
"""

    export_text = (
        CHATGPT_HEADER
        .replace("{{TRACK_NAME}}", json.dumps(track_name))
        .replace("{{RUN_TYPE}}", json.dumps(run_type))
        .replace("{{BASELINE}}", json.dumps(baseline_temp))
        .replace("{{CURRENT}}", json.dumps(current_temp))
        .replace("{{CORNER_FEEDBACK_JSON}}", json.dumps(st.session_state.driver_feedback, indent=2))
        .replace("{{SETUP_RULES_JSON}}", json.dumps(setup_rules, indent=2))
        .replace("{{GATE_GEN}}", "true" if generate_suggestions else "false")
        .replace("{{GATE_PROB}}", "true" if is_problem else "false")
    )

    st.download_button("Download ChatGPT export (.txt)",
                       data=export_text.encode("utf-8"),
                       file_name="chatgpt_corner_export.txt",
                       mime="text/plain")
    st.text_area("Preview", export_text, height=360)
