# pages/ibt_export_python.py
import os
import time
import json
import tempfile
from typing import List, Dict, Any, Optional

import streamlit as st
import pandas as pd

# pip install streamlit pyirsdk pandas pyyaml
import irsdk  # type: ignore
import yaml

st.set_page_config(page_title="IBT Reader (Python) • Export for ChatGPT", layout="wide")
st.title("IBT Reader (Python) • Export for ChatGPT")

st.write(
    "Upload an **.ibt** file, choose channels, or flip **Map all sensors** to include everything. "
    "You’ll get a CSV and a ChatGPT-ready JSON. 100% Python—no extra server."
)

# ----------------- Helpers -----------------
def get_session_info_safe(ir) -> str:
    """Return YAML session info string across pyirsdk variants."""
    for name in ("get_session_info", "getSessionInfo", "get_session_info_str", "get_session_info_string"):
        func = getattr(ir, name, None)
        if callable(func):
            try:
                s = func()
                if isinstance(s, dict):
                    return yaml.safe_dump(s)
                return s or ""
            except Exception:
                pass
    # fallback to telemetry var
    try:
        val = ir["SessionInfo"]
        if isinstance(val, bytes):
            return val.decode("utf-8", "ignore")
        if isinstance(val, str):
            return val
    except Exception:
        pass
    return ""

def discover_channel_names(ir) -> List[str]:
    """Grab all channel names from var headers if available."""
    names: List[str] = []
    try:
        ir.freeze_var_buffer_latest()
        headers = getattr(ir, "_var_headers", None)
        if headers:
            for h in headers:
                if isinstance(h, dict) and h.get("name"):
                    names.append(h["name"])
    except Exception:
        pass
    # unique, keep order
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out

def parse_channels(text: str) -> List[str]:
    return [c.strip() for c in text.split(",") if c.strip()]

def collect_ibt(ibt_path: str, want_channels: Optional[List[str]], map_all: bool, max_seconds: int = 600) -> Dict[str, Any]:
    """
    Read an IBT file using pyirsdk test_file mode.
    If map_all == True, include every channel present.
    Returns dict with rows, channels_found, session_info_yaml, meta, channel_map.
    channel_map: list of {name, first_value}
    """
    ir = irsdk.IRSDK()
    if not ir.startup(test_file=ibt_path):
        raise RuntimeError("Failed to initialize pyirsdk with IBT file.")

    time.sleep(0.05)  # give buffers a beat

    session_info_yaml = get_session_info_safe(ir)

    # discover channels in file
    names_in_file = set(discover_channel_names(ir))

    if map_all:
        channels_found = list(names_in_file) if names_in_file else (want_channels or [])
    else:
        # if we discovered names, filter requested against them; otherwise just trust requested
        if names_in_file:
            channels_found = [c for c in (want_channels or []) if c in names_in_file]
        else:
            channels_found = (want_channels or [])

    # always include helpers when present
    for must in ["Lap", "SessionTime"]:
        if (not names_in_file or must in names_in_file) and must not in channels_found:
            channels_found.append(must)

    rows: List[Dict[str, Any]] = []
    last_session_time = None
    start_time = time.time()
    channel_map: Dict[str, Any] = {}

    while True:
        ir.freeze_var_buffer_latest()
        sample: Dict[str, Any] = {}
        for ch in channels_found:
            try:
                v = ir[ch]
                sample[ch] = v
                if ch not in channel_map and v is not None:
                    channel_map[ch] = v
            except Exception:
                # channel missing for this tick
                pass

        if not sample:
            break

        stime = sample.get("SessionTime", None)
        if last_session_time is not None and stime == last_session_time:
            # EOF
            break
        last_session_time = stime

        rows.append(sample)

        if time.time() - start_time > max_seconds:
            break

    meta = {
        "file": os.path.basename(ibt_path),
        "rows": len(rows),
        "channels_found": len(channels_found),
        "mapped_all": map_all,
    }

    ch_map_list = [{"name": k, "first_value": channel_map.get(k, None)} for k in channels_found]

    ir.shutdown()

    return {
        "rows": rows,
        "channels_found": channels_found,
        "session_info_yaml": session_info_yaml,
        "meta": meta,
        "channel_map": ch_map_list,
    }

def summarize_for_chatgpt(rows: List[Dict[str, Any]], channels: List[str]) -> Dict[str, Any]:
    by_lap: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        lap_raw = r.get("Lap", None)
        try:
            lap = int(lap_raw) if lap_raw is not None else -1
        except Exception:
            lap = -1
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
        for k in ["Speed", "Throttle", "Brake", "RPM", "SteeringWheelAngle", "LatAccel", "LongAccel"]:
            if k in avg:
                row[f"Avg_{k}"] = avg[k]
        lap_stats.append(row)

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
    out: List[str] = []
    best_lap = summary.get("guessBestLap")
    laps = summary.get("laps", [])
    target = next((l for l in laps if l.get("Lap") == best_lap), None)
    if not target:
        return ["No best lap found."]
    avg_throttle = target.get("Avg_Throttle", 0.0)
    avg_brake = target.get("Avg_Brake", 0.0)
    avg_lat = abs(target.get("Avg_LatAccel", 0.0))
    if avg_throttle < 60 and avg_brake > 10:
        out.append("➤ Feels tight mid/exit? Try RR spring perch −1 click (right-click) or −0.5% cross.")
    if avg_throttle > 80 and avg_lat > 1.3:
        out.append("➤ Loose on exit at throttle? Try RF LS rebound +1–2 clicks; +0.5 psi RR.")
    if avg_brake > 20:
        out.append("➤ If entry unstable under braking: +1 click LF rebound, +0.5% cross.")
    if not out:
        out.append("➤ Looks fine on averages. Check corner-specific rules (bus stop, T1/T2).")
    return out

# ----------------- UI -----------------
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

with st.expander("Quick presets"):
    cols = st.columns(2)
    keys = list(PRESETS.keys())
    for i, k in enumerate(keys):
        if cols[i % 2].button(k):
            st.session_state["channels_text"] = PRESETS[k]

map_all = st.checkbox("Map all sensors (include every channel in the file)", value=False)

default_channels = PRESETS["Minimal (fast)"]
channels_text = st.text_area(
    "Channels (comma-separated)",
    value=st.session_state.get("channels_text", default_channels),
    height=110,
    disabled=map_all,
)

uploaded = st.file_uploader("Drop your .ibt file", type=["ibt"])
st.caption("If **Map all sensors** is on, I’ll auto-include every channel found in the file.")

run = st.button("Process IBT", type="primary", disabled=uploaded is None)

# ----------------- Run -----------------
if run and uploaded:
    with st.spinner("Reading IBT…"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ibt") as tmp:
            tmp.write(uploaded.getvalue())
            ibt_path = tmp.name
        try:
            want = parse_channels(channels_text) if not map_all else None
            data = collect_ibt(ibt_path, want, map_all=map_all)
        except Exception as e:
            st.error(f"Parse failed: {e}")
            st.stop()

    rows = data["rows"]
    channels_found = data["channels_found"]
    if not rows:
        st.error("No samples collected. This IBT may be empty or unsupported.")
        st.stop()

    st.success(f"Read {len(rows)} samples • Channels found: {len(channels_found)}")

    # DataFrame with found channels
    # ensure Lap and SessionTime show first if present
    ordered = []
    for k in ["Lap", "SessionTime"]:
        if k in channels_found:
            ordered.append(k)
    for k in channels_found:
        if k not in ordered:
            ordered.append(k)
    df = pd.DataFrame(rows, columns=ordered)

    # Downloads: CSV
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download CSV",
        data=csv_bytes,
        file_name=f"{os.path.splitext(uploaded.name)[0]}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # Build ChatGPT summary JSON
    summary = summarize_for_chatgpt(rows, channels_found)
    json_obj = {
        "meta": data["meta"],
        "summary": summary,
        "sessionInfoYAML": data["session_info_yaml"][:200000],  # clip huge YAML just in case
    }
    json_bytes = json.dumps(json_obj, indent=2).encode("utf-8")
    st.download_button(
        "⬇️ Download ChatGPT JSON",
        data=json_bytes,
        file_name=f"{os.path.splitext(uploaded.name)[0]}.summary.json",
        mime="application/json",
        use_container_width=True,
    )

    # Summary preview
    st.markdown("### Summary Preview")
    st.write(summary["plainSummary"])
    with st.expander("Lap stats (first 30)"):
        st.dataframe(pd.DataFrame(summary["laps"][:30]))

    # Setup suggestions (placeholder)
    st.markdown("### Setup Suggestions (prototype)")
    for s in setup_suggestions_stub(summary):
        st.write(s)

    # Channel map display + download
    st.markdown("### Channel Map")
    ch_map_df = pd.DataFrame(data["channel_map"])
    st.dataframe(ch_map_df, use_container_width=True, height=280)
    ch_map_csv = ch_map_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download Channel Map (CSV)",
        data=ch_map_csv,
        file_name=f"{os.path.splitext(uploaded.name)[0]}.channel_map.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # Session YAML peek
    with st.expander("SessionInfo (YAML) — first 2000 chars"):
        st.code((data["session_info_yaml"] or "")[:2000], language="yaml")
