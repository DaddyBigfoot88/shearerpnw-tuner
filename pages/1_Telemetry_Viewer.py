import json
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.title("📊 Telemetry Viewer (CSV for now)")
st.caption("Upload a CSV with columns like: Lap, LapDistPct, Speed, Throttle, Brake. IBT support coming next.")

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

