# Setup Coach – JSON-driven rules + tracks metadata (left/right, banking, angle) + temp comp
import json, pathlib, re
import streamlit as st

st.set_page_config(layout='wide')
st.title('Setup Coach (Question Mode)')
st.caption('Rules + corner metadata loaded from JSON. No need to edit this page to tune logic.')

TRACKS_META_PATH = pathlib.Path('ShearerPNW_Easy_Tuner_Editables/tracks_meta.json')
RULES_PATH       = pathlib.Path('ShearerPNW_Easy_Tuner_Editables/coach_rules.json')
SETUP_RULES_PATH = pathlib.Path('ShearerPNW_Easy_Tuner_Editables/setup_rules_nextgen.json')

def load_json(path, fallback):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:
        st.error(f'Error reading {path}: {e}')
    return fallback

tracks_meta = load_json(TRACKS_META_PATH, {})
coach_rules = load_json(RULES_PATH, {})
setup_rules = load_json(SETUP_RULES_PATH, {
    'allowed_parameters': {
        'tires': ['LF_pressure','RF_pressure','LR_pressure','RR_pressure'],
        'suspension': [
            'LF_shock_rebound_clicks','RF_shock_rebound_clicks','LR_shock_rebound_clicks','RR_shock_rebound_clicks',
            'LF_shock_bump_clicks','RF_shock_bump_clicks','LR_shock_bump_clicks','RR_shock_bump_clicks',
            'front_swaybar_stiffness','rear_swaybar_stiffness','front_spring_rate','rear_spring_rate'
        ],
        'chassis': ['crossweight_percent','front_ride_height_in','rear_ride_height_in','rear_trackbar_in'],
        'rear_end': ['diff_preload_ftlbs','gear_note']
    },
    'limits': {
        'pressure': {'min_psig': 10.0, 'max_psig': 60.0, 'increments_psig': 0.5},
        'shock_clicks': {'min_clicks': 0, 'max_clicks': 10, 'increments': 1},
        'spring_rate': {'min_lbin': 100, 'max_lbin': 2200, 'increments': 25},
        'ride_height': {'min_in': 2.0, 'max_in': 6.0, 'increments': 0.05},
        'crossweight': {'min_pct': 45.0, 'max_pct': 55.0, 'increments': 0.1},
        'trackbar': {'min_in': 5.0, 'max_in': 12.0, 'increments': 0.25},
        'diff_preload': {'min_ftlbs': 0, 'max_ftlbs': 75, 'increments': 5}
    }
})

ALLOWED = setup_rules.get('allowed_parameters', {})
LIM     = setup_rules.get('limits', {})

def sev_bucket(n):
    return 'slight' if n <= 3 else ('moderate' if n <= 7 else 'severe')

def mk_delta(name, delta, units):
    sign = '+' if float(delta) > 0 else ''
    return f'{name}: {sign}{float(delta):g}{units}'

def mirror_sides(d):
    def swap_one(txt):
        txt = txt.replace('LF_', '__TMPF__')
        txt = txt.replace('RF_', 'LF_')
        txt = txt.replace('__TMPF__', 'RF_')
        txt = txt.replace('LR_', '__TMPR__')
        txt = txt.replace('RR_', 'LR_')
        txt = txt.replace('__TMPR__', 'RR_')
        return txt
    return {k: [swap_one(x) for x in v] for k, v in d.items()}
def step_for_param(pname: str):
    p = pname.lower()
    if 'pressure' in p:   return LIM.get('pressure', {}).get('increments_psig', 0.5)
    if 'shock' in p and 'click' in p: return LIM.get('shock_clicks', {}).get('increments', 1)
    if 'spring_rate' in p:return LIM.get('spring_rate', {}).get('increments', 25)
    if 'crossweight' in p:return LIM.get('crossweight', {}).get('increments', 0.1)
    if 'trackbar' in p:   return LIM.get('trackbar', {}).get('increments', 0.25)
    if 'ride_height' in p:return LIM.get('ride_height', {}).get('increments', 0.05)
    if 'diff_preload' in p:return LIM.get('diff_preload', {}).get('increments', 5)
    return 1.0

def scale_in_text(txt: str, factor: float):
    m = re.search(r'([+-]?\d+(\.\d+)?)', txt)
    if not m:
        return txt
    param = txt.split(':',1)[0]
    step  = step_for_param(param)
    val   = float(m.group(1)) * float(factor)
    snapped = round(val / step) * step
    new_num = f'{snapped:g}'
    s, e = m.span(1)
    return txt[:s] + new_num + txt[e:]

def scale_block(d, factor: float):
    return {k: [scale_in_text(x, factor) for x in v] for k, v in d.items()}

def ensure_allowed(d):
    out = {k: [] for k in d.keys()}
    allow_flat = set()
    for cat, plist in ALLOWED.items():
        for p in plist:
            allow_flat.add(p)
    for cat, arr in d.items():
        for line in arr:
            pname = line.split(':',1)[0]
            if pname in allow_flat:
                out[cat].append(line)
    return out

def merge_accum(to, add):
    for k in add:
        to.setdefault(k, [])
        to[k].extend(add[k])

with st.sidebar:
    track_names = sorted(list(tracks_meta.keys())) if tracks_meta else ['Unknown Track']
    idx = track_names.index('Watkins Glen International (Cup)') if 'Watkins Glen International (Cup)' in track_names else 0
    track_pick = st.selectbox('Track', track_names, index=idx)
    run_type = st.radio('Run type', ['Practice','Qualifying','Race'], index=0, horizontal=True)

track_obj = tracks_meta.get(track_pick, {'corners':[{'name':'T1','dir':'M','bank_deg':0,'angle_deg':90}]})
corner_meta = track_obj.get('corners', [])
corner_labels = [c.get('name','Corner') for c in corner_meta]

st.header('Corner Feel')
DEFAULT_FEELINGS = [
    'No issue / skip',
    'Loose on entry','Loose mid-corner','Loose on exit',
    'Tight on entry','Tight mid-corner','Tight on exit',
    'Brakes locking','Traction wheelspin','Porpoising / Bottoming','Other'
]
if 'coach_feedback' not in st.session_state or st.session_state.get('_coach_track') != track_pick:
    st.session_state.coach_feedback = {c: {'feels':'No issue / skip','severity':0,'note':''} for c in corner_labels}
    st.session_state._coach_track = track_pick

cols = st.columns(3)
for i, meta in enumerate(corner_meta):
    c = meta.get('name','Corner')
    with cols[i % 3]:
        dlabel = {'L':'Left','R':'Right','M':'Mixed/Unknown'}.get(meta.get('dir','M'),'Mixed/Unknown')
        st.markdown(f"**{c}**  \n<small>Dir: {dlabel} • Bank: {meta.get('bank_deg',0):g}° • Angle: {meta.get('angle_deg',90):g}°</small>", unsafe_allow_html=True)
        feels = st.selectbox(f'{c} feel', DEFAULT_FEELINGS, index=0, key=f'feel_{i}')
        severity = st.slider(f'{c} severity', 0, 10, st.session_state.coach_feedback[c].get('severity',0), key=f'sev_{i}')
        note = st.text_input(f'{c} note', value=st.session_state.coach_feedback[c].get('note',''), key=f'note_{i}')
        st.session_state.coach_feedback[c] = {'feels': feels, 'severity': int(severity), 'note': note}

st.markdown('---')
st.caption('Severity: 1–3 slight · 4–7 moderate · 8–10 severe')

st.header('Track Temperature Compensation')
base_default = track_obj.get('baseline_temp_f', coach_rules.get('defaults', {}).get('baseline_temp_f', 85))
c1, c2 = st.columns(2)
with c1:
    baseline_temp = st.number_input('Baseline Setup Temperature (°F)', 40, 150, int(base_default))
with c2:
    current_temp = st.number_input('Current Track Temperature (°F)', 40, 150, int(base_default))

feel_key_map = coach_rules.get('feel_key_map', {})
scaling_cfg  = coach_rules.get('scaling', {})
temp_cfg     = coach_rules.get('temp_comp', {})

def build_block_from_json(rule_block: dict, sev_key: str):
    out = {'tires': [], 'chassis': [], 'suspension': [], 'rear_end': []}
    for cat, params in rule_block.items():
        for pname, cfg in params.items():
            delta = cfg.get('delta', {}).get(sev_key, 0)
            units = cfg.get('units', '')
            if delta:
                out[cat].append(mk_delta(pname, delta, units))
    return out

def apply_temp_comp(baseline, current):
    diff = current - baseline
    ad = abs(diff)
    dead = temp_cfg.get('deadband_f', 5)
    if ad <= dead:
        return {'tires':[], 'chassis':[], 'suspension':[], 'rear_end':[]}, diff, 0
    steps = 1 if ad <= 10 else (2 if ad <= 20 else 3)
    sev_key = {1:'slight',2:'moderate',3:'severe'}[steps]
    block = temp_cfg.get('hotter', {}) if diff > 0 else temp_cfg.get('cooler', {})
    return build_block_from_json(block, sev_key), diff, steps

def bank_angle_factor(bank_deg: float, angle_deg: float):
    if bank_deg <= scaling_cfg.get('bank_low_deg', 4): bf = scaling_cfg.get('bank_low_mult', 1.25)
    elif bank_deg <= scaling_cfg.get('bank_mid_deg', 12): bf = scaling_cfg.get('bank_mid_mult', 1.0)
    else: bf = scaling_cfg.get('bank_high_mult', 0.8)
    if angle_deg >= scaling_cfg.get('angle_high_deg', 120): af = scaling_cfg.get('angle_high_mult', 1.25)
    elif angle_deg >= scaling_cfg.get('angle_mid_deg', 60): af = scaling_cfg.get('angle_mid_mult', 1.0)
    else: af = scaling_cfg.get('angle_low_mult', 0.85)
    return bf * af

btn = st.button('Compute Suggestions')
if btn:
    plan = {'tires': [], 'chassis': [], 'suspension': [], 'rear_end': []}
    findings = []

    tblock, tdiff, tscale = apply_temp_comp(baseline_temp, current_temp)
    plan = {k: [] for k in plan}
    for k, v in ensure_allowed(tblock).items():
        plan[k].extend(v)
    if tscale > 0:
        findings.append(f'Temperature: {abs(tdiff)}°F {'+'hotter'+' if tdiff>0 else '+'cooler'+'} than baseline (x{tscale})')

    for meta in corner_meta:
        name = meta.get('name','Corner')
        fb = st.session_state.coach_feedback.get(name, {'feels':'No issue / skip','severity':0})
        if fb['feels'] == 'No issue / skip' or fb['severity'] <= 0:
            continue
        sev = sev_bucket(fb['severity'])
        key = feel_key_map.get(fb['feels'])
        if not key:
            continue
        block = coach_rules.get('symptoms', {}).get(key, {})
        sb = build_block_from_json(block, sev)

        factor = bank_angle_factor(float(meta.get('bank_deg',0)), float(meta.get('angle_deg',90)))
        sb = {k: [scale_in_text(x, factor) for x in v] for k, v in sb.items()}

        if str(meta.get('dir','M')).upper().startswith('R'):
            sb = mirror_sides(sb)

        sb = ensure_allowed(sb)
        for k, v in sb.items():
            plan[k].extend(v)

        findings.append(f"{name} ({'Right' if str(meta.get('dir','M')).upper().startswith('R') else 'Left/Mixed'}; bank {meta.get('bank_deg',0):g}°, angle {meta.get('angle_deg',90):g}°): {fb['feels']} ({sev})")

    if not any(plan.values()) and not findings:
        st.info('No problems and temps near baseline. Nothing to change.')
    else:
        st.subheader('Key Findings')
        for f in findings:
            st.write(f'- {f}')

        st.subheader('Setup Changes')
        for cat in ['tires','chassis','suspension','rear_end']:
            if plan[cat]:
                st.markdown(f'**{cat.title()}**')
                for line in plan[cat]:
                    st.write(f'- {line}')

        st.subheader('Next Run Checklist')
        st.write('- Did each corner get better? Any new side effects? Re-test in small steps.')

        export = {
            'track': track_pick,
            'run_type': run_type,
            'baseline_temp_f': baseline_temp,
            'current_temp_f': current_temp,
            'findings': findings,
            'recommendations': plan
        }
        st.download_button('Download plan (.json)',
            data=json.dumps(export, indent=2).encode('utf-8'),
            file_name='setup_coach_plan.json', mime='application/json')
else:
    st.info('Pick corners, set temps, then Compute Suggestions.')
