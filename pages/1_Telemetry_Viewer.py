
# Telemetry Viewer — no auto-prefetch; fetch only when you click the button
import io, json, os, pathlib, tempfile, re, mimetypes
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import requests

st.set_page_config(layout="wide")
st.title("Telemetry Viewer")
st.caption("Maps are cached locally. No auto-download. Click the sidebar button to fetch/refresh a map.")

def slug(s: str):
    return re.sub(r'[^a-z0-9_]+', '_', s.lower())

TRACKS_JSON_PATH = pathlib.Path("ShearerPNW_Easy_Tuner_Editables/tracks.json")
ASSETS_DIR = pathlib.Path("assets/tracks")
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

def load_tracks():
    if not TRACKS_JSON_PATH.exists():
        st.error("Missing ShearerPNW_Easy_Tuner_Editables/tracks.json")
        return {}
    try:
        return json.loads(TRACKS_JSON_PATH.read_text())
    except Exception as e:
        st.error(f"tracks.json error: {e}")
        return {}

def save_tracks(tracks_obj):
    try:
        TRACKS_JSON_PATH.write_text(json.dumps(tracks_obj, indent=2))
        return True
    except Exception as e:
        st.error(f"Failed to save tracks.json: {e}")
        return False

ACCEPTABLE_LICENSES = {"public domain","cc0","cc-by","cc by","cc-by-sa","cc by-sa","cc-by 2.0","cc-by-sa 3.0","cc-by-sa 4.0"}
UA = {"User-Agent": "ShearerPNW-TrackPrefetch/1.0 (educational use)"}

def commons_search_image(query: str):
    api = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query + " track layout OR circuit map OR track map OR aerial OR satellite",
        "gsrlimit": 12,
        "gsrnamespace": 6,  # FILE namespace
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 2000,
        "origin": "*"
    }
    r = requests.get(api, params=params, headers=UA, timeout=40)
    r.raise_for_status()
    data = r.json()
    if "query" not in data or "pages" not in data["query"]:
        return None
    pages = list(data["query"]["pages"].values())
    # prefer layout-ish first
    layout_pages, other_pages = [], []
    for p in pages:
        title = (p.get("title") or "").lower()
        if any(k in title for k in ("layout","map","circuit","track")):
            layout_pages.append(p)
        else:
            other_pages.append(p)
    pages = layout_pages + other_pages
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        ext = info.get("extmetadata", {}) or {}
        lic = (ext.get("LicenseShortName", {}).get("value","") or ext.get("License", {}).get("value","")).lower()
        if any(k in lic for k in ACCEPTABLE_LICENSES):
            artist_raw = (ext.get("Artist", {}).get("value","") or "")
            artist = re.sub(r"<.*?>","", artist_raw).strip()
            return {
                "title": p.get("title",""),
                "url": info.get("url") or info.get("thumburl"),
                "license": ext.get("LicenseShortName", {}).get("value") or ext.get("License", {}).get("value",""),
                "artist": artist,
                "source": "https://commons.wikimedia.org/wiki/" + (p.get("title","").replace(" ", "_"))
            }
    return None

def download_and_set(track_name: str, track_id: str, img_url: str, credit: dict, tracks_obj: dict):
    try:
        r = requests.get(img_url, headers=UA, timeout=60)
        r.raise_for_status()
    except Exception as e:
        st.error(f"Download failed: {e}")
        return False
    ctype = r.headers.get("Content-Type","").split(";")[0].strip().lower()
    ext = mimetypes.guess_extension(ctype) or os.path.splitext(img_url)[1] or ".jpg"
    if ext.lower() not in (".png",".jpg",".jpeg",".webp",".svg"):
        ext = ".jpg"
    out_path = ASSETS_DIR / f"{track_id}{ext}"
    with open(out_path, "wb") as f:
        f.write(r.content)
    if track_name in tracks_obj:
        tracks_obj[track_name]["image"] = str(out_path)
        tracks_obj[track_name]["credit"] = credit
        save_tracks(tracks_obj)
    return True

# Sidebar controls
with st.sidebar:
    tracks = load_tracks()
    track_names = sorted(list(tracks.keys())) if tracks else ["Unknown Track"]
    default_idx = track_names.index("Watkins Glen International (Cup)") if "Watkins Glen International (Cup)" in track_names else 0
    track_pick = st.selectbox("Track", track_names, index=default_idx)
    track_info = tracks.get(track_pick, {"id":"unknown","corners": ["T1","T2","T3"]})
    fetch_now = st.button("Fetch/Refresh this track map (one-time)")
    up = st.file_uploader("Upload telemetry (.csv or .ibt)", type=["csv","ibt"])

# Track image
colA, colB = st.columns([1.2, 1.8])
with colA:
    st.subheader("Track")
    img_path = track_info.get("image")
    if fetch_now:
        q = track_pick.split("(")[0].strip()
        result = commons_search_image(q)
        if result and result.get("url"):
            ok = download_and_set(
                track_pick,
                track_info.get("id","unknown"),
                result["url"],
                {
                    "title": result.get("title",""),
                    "author": result.get("artist",""),
                    "license": result.get("license",""),
                    "source": result.get("source","")
                },
                tracks
            )
            if ok:
                img_path = tracks.get(track_pick, {}).get("image")
                st.success("Map fetched and cached.")
        else:
            st.error("Could not find a suitable image. Try again later.")

    if img_path and pathlib.Path(img_path).exists():
        st.image(img_path, use_container_width=True, caption=str(track_pick))
    else:
        st.warning("No image cached yet. Use the button in the sidebar to fetch it once.")

# Telemetry load (CSV/IBT minimal)
with colB:
    st.subheader("Channels and File info")
    df = None

    def coerce_min_columns(df):
        notes = []
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

    if up is not None:
        suffix = pathlib.Path(up.name).suffix.lower()
        if suffix == ".csv":
            try:
                df = pd.read_csv(up)
            except Exception as e:
                st.error(f"CSV read error: {e}")
        elif suffix == ".ibt":
            try:
                import irsdk, tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".ibt") as tmp:
                    tmp.write(up.read()); tmp_path = tmp.name
                ibt = None
                if hasattr(irsdk, "IBT"): ibt = irsdk.IBT(tmp_path)
                elif hasattr(irsdk, "ibt"): ibt = irsdk.ibt.IBT(tmp_path)
                if ibt is None: raise RuntimeError("pyirsdk.IBT class not found")
                try:
                    if hasattr(ibt, "open"): ibt.open()
                except Exception: pass
                want = ["Lap","LapDistPct","LapDist","Speed","Throttle","Brake","SteeringWheelAngle","YawRate"]
                data = {}
                for ch in want:
                    arr = None
                    for getter in ("get","get_channel","get_channel_data_by_name"):
                        try:
                            fn = getattr(ibt, getter); maybe = fn(ch)
                            if maybe is not None: arr = maybe; break
                        except Exception: continue
                    if arr is not None: data[ch] = arr
                if not data: raise RuntimeError("No known channels found in IBT.")
                df = pd.DataFrame(data).dropna(how="all")
                # normalize throttle/brake to percent if they look 0..1
                for col in ("Throttle","Brake"):
                    if col in df.columns:
                        try:
                            if float(df[col].max()) <= 1.5:
                                df[col] = (df[col] * 100.0).clip(0,100)
                        except Exception:
                            pass
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
            except Exception as e:
                st.error(f"IBT parse error: {e}")
            finally:
                try:
                    if 'ibt' in locals() and hasattr(ibt, "close"): ibt.close()
                except Exception: pass
                try: os.unlink(tmp_path)
                except Exception: pass

    if df is not None:
        df, notes = coerce_min_columns(df)
        if notes: st.warning("Synthesized columns: " + ", ".join(notes))
        st.write(", ".join(list(df.columns)))

# Keep the rest minimal to avoid syntax issues
st.markdown("---")
st.caption("ShearerPNW Telemetry Viewer — no auto-prefetch build")
