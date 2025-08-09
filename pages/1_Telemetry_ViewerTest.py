import os
import tempfile
import time
import json
from typing import List, Dict, Any

import streamlit as st
import pandas as pd

# pyirsdk reads IBT files in "test_file" mode
# pip install pyirsdk
import irsdk  # type: ignore

st.set_page_config(page_title="IBT Reader (Python) • Export for ChatGPT", layout="wide")
st.title("IBT Reader (Python) • Export for ChatGPT")

st.write(
    "Upload an **.ibt** file, choose your channels, and I’ll kick out a CSV plus a ChatGPT-ready JSON summary. "
    "This runs 100% in Streamlit (no Node server)."
)

# ---------- Presets ----------
PRESETS = {
    "Minimal (fast)": "Lap, LapDistPct, Speed, Throttle, Brake, Gear, RPM, SteeringWheelAngle, LatAccel, LongAccel, TrackTemp, FuelLevel",
    "Handling & Balance": "Lap, LapDistPct, Speed, Throttle, Brake, SteeringWheelAngle, LatAccel, LongAccel, Yaw, Pitch, Roll, WheelSlipFL, WheelSlipFR, WheelSlipRL, WheelSlipRR, TireCarcassTempFL, TireCarcassTempFR, TireCarcassTempRL, TireCarcassTempRR",
    "Tires: Temps & Pressures": "LFtempCL, LFtempCM, LFtempCR, RFtempCL, RFtempCM, RFtempCR, LRtempCL, LRtempCM, LRtempCR, RRtempCL, RRtempCM, RRtempCR, LFpressure, RFpressure, LRpressure, RRpressure, LFwear, RFwear, LRwear, RRwear",
    "Ride Height / Platform": "LFrideHeight, RFrideHeight, LRrideHeight, RRrideHeight, CFSRrideHeight, SplitterHeight, Rake, AeroBalance, Downforce, Drag",
    "Shocks & Travel": "LFshockDefl, RFshockDefl, LRshockDefl, RRshockDefl, LFshockVel, RFshockVel, LRshockVel, RRshockVel, LFshockPos, RFshockPos, LRshockPos, RRshockPos",
    "Wheel speed & Drivetrain": "WheelSpeedFL, WheelSpeedFR, WheelSpeedRL, WheelSpeedRR, Clutch, EngineTorque, Power, SlipRatioFL, SlipRatioFR, SlipRatioRL, SlipRatioRR",
    "Laps / Flags / Incidents": "Lap, LapBestLap, LapBestLapTime, SessionTime, PlayerCarMyIncidentCount, PlayerCarDriverIncidentCount, PlayerCarTeamIncidentCount",
    "GPS / Line": "Lat, Lon",
}

with st.expander("Quick presets (click to fill the box)"):
    cols = st.columns(2)
    keys = list(PRESETS.keys())
    for i, k in enumerate(keys):
        if cols[i % 2].button(k):
            st.session_state["channels_text"] = PRESETS[k]

default_channels = PRESETS["Minimal (fast)"]
channels_text = st.text_area(
    "Channels (comma-separated)",
    value=st.session_state.get("channels_text", default_channels),
    height=100,
)

uploaded = st.file_uploader("Drop your .ibt file", type=["ibt"])
st.caption("Tip: You can paste BIG lists. Missing channels will be skipped if not in the file.")

run = st.button("Process IBT", type="primary", disabled=uploaded is None)

def parse_channels(text: str) -> List[str]:
    return [c.strip() for c in text.split(",") if c.strip()]

def collect_ibt_samples(ibt_path: str, want_channels: List[str], max_seconds: int = 600) -> Dict[str, Any]:
    """
    Read an IBT file using pyirsdk in test_file mode and iterate samples forward.
    Returns a dict with:
      channels_found, rows (list[dict]), meta, session_info_yaml
    """
    ir = irsdk.IRSDK()
    # Open the IBT as a test file
    if not ir.startup(test_file=ibt_path):
        raise RuntimeError("Failed to initialize pyirsdk with IBT file.")

    # A small wait to ensure buffers are ready
    time.sleep(0.05)

    # Read session info (YAML string)
    session_info_yaml = ir.get_session_info() or ""

    rows = []
    channels_found = []
    last_session_time = None
    start_time = time.time()

    # Try to detect which requested channels actually exist
    # pyirsdk exposes var headers list via ._var_headers after freeze call, so we do one freeze first
    ir.freeze_var_buffer_latest()
    try:
        headers = ir._var_headers  # pyirsdk internal field; works in practice
        names_in_file = {h["name"] for h in headers} if headers else set()
    except Exception:
        names_in_file = set()

    # If we could discover names, filter. Otherwise just keep requested list.
    if names_in_file:
        channels_found = [c for c in want_channels if c in names_in_file]
    else:
        channels_found = want_channels[:]  # best effort if header list not available

    # Always include Lap and SessionTime if available
    for must in ["Lap", "SessionTime"]:
        if must in names_in_file and must not in channels_found:
            channels_found.append(must)

    # Walk forward through the file, capturing samples.
    # In test_file mode, pyirsdk advances its internal pointer when we call freeze_var_buffer_latest()
    # We'll stop when SessionTime stops changing or we hit time/row limits.
    while True:
        ir.freeze_var_buffer_latest()
        sample = {}
        for ch in channels_found:
            try:
                sample[ch] = ir[ch]
            except Exception:
                # channel missing for this tick; skip
                pass

        # If nothing read, bail
        if not sample:
            break

        stime = sample.get("SessionTime", None)

        # Detect end: if SessionTime repeats (EOF) or we’ve been running too long
        if last_session_time is not None and stime == last_session_time:
            break
        last_session_time = stime

        rows.append(sample)

        # simple safety stop: don't chew forever
        if time.time() - start_time > max_seconds:
            break

        # yield a little so Streamlit UI stays responsive
        time.sleep(0.0)

    # Try to get tick rate from headers if present
    meta = {
        "file": os.path.basename(ibt_path),
        "rows": len(rows),
        "channels_found": channels_found,
    }

    ir.shutdown()
    return {
        "channels_found": channels_found,
        "rows": rows,
        "meta": meta,
        "session_info_yaml": session_info_yaml,
    }

def summarize_for_chatgpt(rows: List[Dict[str, Any]], channels: List[str]) -> Dict[str, Any]:
    # Build simple lap aggregates
    by_lap: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        lap = int(r.get("Lap", -1)) if r.get("Lap", None) is not None else -1
        if lap < 0:
            continue
        bucket = by_lap.setdefault(lap, {"count": 0, "sums": {}})
        bucket["count"] += 1
        for k, v in r.items():
            if isinstance(v, (int, float)):
                bucket["sums"][k] = bucket["sums"].get(k, 0.0) + float(v)

    lap_stats = []
    for lap, b in sorted(by_lap.items()):
        if b["count"] == 0:
            continue
        avg = {k: v / b["count"] for k, v in b["sums"].items()}
        row = {"Lap": lap, "Samples": b["count"]}
        # include some common ones if present
        for k in ["Speed", "Throttle", "Brake", "RPM", "SteeringWheelAngle", "LatAccel", "LongAccel"]:
            if k in avg:
                row[f"Avg_{k}"] = avg[k]
        lap_stats.append(row)

    # naive “best” lap guess: highest Avg_Speed
    best = None
    if lap_stats:
        best = max(lap_stats, key=lambda x: x.get("Avg_Speed", 0))

    summary_text = (
        f"Best lap guess: Lap {best['Lap']} — Avg speed ~{round(best.get('Avg_Speed', 0))} "
        f"Throttle ~{best.get('Avg_Throttle', 0):.1f}% Brake ~{best.get('Avg_Brake', 0):.1f}%"
        if best else "Could not determine best lap."
    )

    return {
        "channels": channels,
        "laps": lap_stats[:1000],
        "guessBestLap": best["Lap"] if best else None,
        "plainSummary": summary_text,
    }

def setup_suggestions_stub(summary: Dict[str, Any]) -> List[str]:
    """
    Simple placeholder: reads lap averages and prints human-readable suggestions.
    Replace with your real rules (Watkins Glen corner rules, severity mapping, etc.).
    """
    out = []
    best_lap = summary.get("guessBestLap")
    laps = summary.get("laps", [])
    target = next((l for l in laps if l.get("Lap") == best_lap), None)
    if not target:
        return ["No best lap found."]

    # Very basic heuristics (just something to show in the UI)
    avg_throttle = target.get("Avg_Throttle", 0.0)
    avg_brake = target.get("Avg_Brake", 0.0)
    avg_lat = abs(target.get("Avg_LatAccel", 0.0))
    if avg_throttle < 60 and avg_brake > 10:
        out.append("➤ Might be tight mid/exit. Try: RR spring perch −1 click (right-click), or −0.5% cross.")
    if avg_throttle > 80 and avg_lat > 1.3:
        out.append("➤ Might be loose on exit at throttle. Try: RF LS rebound +1–2 clicks; +0.5 psi RR.")
    if avg_brake > 20:
        out.append("➤ Heavy braking average. If entry unstable: +1 click LF rebound, +0.5% cross.")

    if not out:
        out.append("➤ Balance looks okay on averages. Check corner-specific rules for bus stop and T1/T2.")
    return out

if run and uploaded:
    with st.spinner("Reading IBT (Python)…"):
        # Save uploaded IBT to a temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ibt") as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name

        try:
            want = parse_channels(channels_text)
            data = collect_ibt_samples(tmp_path, want)
        except Exception as e:
            st.error(f"Parse failed: {e}")
            st.stop()
        finally:
            # keep tmp file for a moment so user can retry without reupload if needed
            pass

    rows = data["rows"]
    channels_found = data["channels_found"]
    if not rows:
        st.error("No samples collected. This IBT may be empty or unsupported.")
        st.stop()

    st.success(f"Read {len(rows)} samples • Channels found: {len(channels_found)}")

    # Build DataFrame with only found channels
    # Fill missing cols with NaN for a clean CSV header
    all_cols = []
    for c in channels_found:
        if c not in all_cols:
            all_cols.append(c)
    # Ensure Lap and SessionTime are first if present
    ordered = [c for c in ["Lap", "SessionTime"] if c in all_cols] + [c for c in all_cols if c not in ["Lap", "SessionTime"]]
    df = pd.DataFrame(rows, columns=ordered)

    # Downloads
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download CSV", data=csv_bytes, file_name=f"{os.path.splitext(uploaded.name)[0]}.csv", mime="text/csv", use_container_width=True)

    # Build ChatGPT summary JSON
    summary = summarize_for_chatgpt(rows, channels_found)
    json_bytes = json.dumps({
        "meta": data["meta"],
        "summary": summary,
        "sessionInfoYAML": data["session_info_yaml"][:200000],  # clip huge YAML
    }, indent=2).encode("utf-8")
    st.download_button("⬇️ Download ChatGPT JSON", data=json_bytes, file_name=f"{os.path.splitext(uploaded.name)[0]}.summary.json", mime="application/json", use_container_width=True)

    # Quick preview
    st.markdown("### Summary Preview")
    st.write(summary["plainSummary"])
    with st.expander("Lap stats (first 30)"):
        st.dataframe(pd.DataFrame(summary["laps"][:30]))

    # Setup suggestions (placeholder)
    st.markdown("### Setup Suggestions (prototype)")
    for s in setup_suggestions_stub(summary):
        st.write(s)

    # Peek at YAML header if you want WeekendInfo etc.
    with st.expander("SessionInfo (YAML) — first 2000 chars"):
        st.code((data["session_info_yaml"] or "")[:2000], language="yaml")
