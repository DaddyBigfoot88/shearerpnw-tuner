# pages/ibt_export_python.py
import os
import time
import json
import tempfile
from typing import List, Dict, Any

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
    names = []
    try:
        ir.freeze_var_buffer_latest()
        headers = getattr(ir, "_var_headers", None)
        if headers:
            names = [h.get("name") for h in headers if isinstance(h, dict) and h.get("name")]
    except Exception:
        pass
    # unique order-preserving
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out

def parse_channels(text: str) -> List[str]:
    return [c.strip() for c in text.split(",") if c.strip()]

def collect_ibt(ibt_path: str, want_channels: List[str] | None, map_all: bool, max_seconds: int = 600) -> Dict[str, Any]:
    """
    Read an IBT file using pyirsdk test_file mode.
    If map_all == True, gather *all* channels present.
    Returns dict with rows, channels_found, session_info_yaml, meta, channel_map.
    channel_map: list of {name, first_value}
    """
    ir = irsdk.IRSDK()
    if not ir.startup(test_file=ibt_path):
        raise RuntimeError("Failed to initialize pyirsdk with IBT file.")

    time.sleep(0.05)

    session_info_yaml = get_session_info_safe(ir)

    # discover channels present in file
    names_in_file = set(discover_channel_names(ir))
    if map_all:
        channels_found = list(names_in_file) if names_in_file else (want_channels or [])
    else:
        channels_found = [c for c in (want_channels or []) if (not names_in_file or c in names_in_file)]

    # always include Lap and SessionTime when present
    for must in ["Lap", "SessionTime"]:
        if (not names_in_file or must in names_in_file) and must not in channels_found:
            channels_found.append(must)

    rows = []
    last_session_time = None
    start_time = time.time()
    channel_map = {}  # name -> first non-None value

    while True:
        ir.freeze_var_buffer_latest()
        sample = {}
        for ch in channels_found:
            try:
                v = ir[ch]
                sample[ch] = v
                if ch not in channel_map and v is not None:
                    channel_map[ch] = v
            except Exception:
                pass

        if not sample:
            break

        stime = sample.get("SessionTime", None)
        if last_session_time is not None and stime == last_session_time:
            # end of file
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

    # turn channel_map into a stable list for display/export
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
        lap = r.get("Lap", None)
        try:
            lap = int(lap) if lap is not None else -1
        except Exception:
            lap = -1
        if lap < 0:
            continue
        b = by_lap.setdefault(lap, {"count": 0, "sums": {}})
        b["count"] += 1
        for k, v in r.items():
            if isinstance(v, (int, float)):
                b["sums"][k] = b["sums"].get(k, 0.0) + float(v)

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
    out = []
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
    "Minimal (fast)": "Lap, LapDistPct, Speed, Throttle, Brake, Gear, RPM, SteeringWheelAngle
