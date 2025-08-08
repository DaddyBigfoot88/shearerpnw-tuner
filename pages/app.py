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

