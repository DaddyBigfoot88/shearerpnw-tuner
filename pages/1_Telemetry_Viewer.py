# 1_Telemetry_Viewer.py
# Streamlit Telemetry Viewer (updated)
# - Uploader sits under the "Run type" tab
# - Tolerant IBT loader: won’t hard-crash if common channels are missing

import os
import io
import tempfile
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Telemetry Viewer", layout="wide")

# =========================
# Helpers
# =========================

def tolerant_load_ibt(file_bytes: bytes) -> pd.DataFrame:
    """
    Read an .ibt with pyirsdk/irsdk.
    If usual channels aren’t present, fall back to dumping any numeric 1-D data.
    Returns a DataFrame. Raises RuntimeError with a clear message if unreadable.
    """
    try:
        import irsdk  # pyirsdk
    except Exception as e:
        raise RuntimeError("pyirsdk/irsdk not installed. Add 'pyirsdk' to requirements.txt.") from e

    tmp_path = None
    ibt = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ibt") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        # Try constructor variations
        if hasattr(irsdk, "IBT"):
            try:
                ibt = irsdk.IBT(tmp_path)
            except TypeError:
                ibt = irsdk.IBT()
                try:
                    ibt.open(tmp_path)
                except TypeError:
                    pass
        if ibt is None and hasattr(irsdk, "ibt"):
            try:
                ibt = irsdk.ibt.IBT(tmp_path)
            except TypeError:
                ibt = irsdk.ibt.IBT()
                try:
                    ibt.open(tmp_path)
                except TypeError:
                    pass

        if ibt is None:
            raise RuntimeError("Couldn't create IBT reader (irsdk.IBT).")

        # Ensure open
        if hasattr(ibt, "open"):
            try:
                ibt.open()
            except TypeError:
                ibt.open(tmp_path)

        # function to try fetching a channel by name
        def read_channel(name):
            for m in ("get_channel_data_by_name", "get", "getVar", "get_var", "read_channel"):
                fn = getattr(ibt, m, None)
                if callable(fn):
                    try:
                        val = fn(name)
                        if val is not None:
                            return val
                    except Exception:
                        continue
            return None

        # try the usual suspects
        want = ["Lap", "LapDistPct", "LapDist", "Speed", "Throttle", "Brake", "SteeringWheelAngle", "YawRate"]
        data: Dict[str, np.ndarray] = {}
        for ch in want:
            arr = read_channel(ch)
            if arr is not None:
                try:
                    a = np.asarray(arr)
                    if a.size > 0:
                        data[ch] = a
                except Exception:
                    pass

        # If none of those were found, try to dump everything
        if not data:
            dump = None
            read_fn = getattr(ibt, "read", None)
            if callable(read_fn):
                for args in [(), (0, -1)]:
                    try:
                        dump = read_fn(*args)
                        if isinstance(dump, dict) and dump:
                            break
                    except Exception:
                        continue

            if isinstance(dump, dict) and dump:
                df_all = {}
                for k, v in dump.items():
                    try:
                        a = np.asarray(v)
                        if a.ndim == 1 and np.issubdtype(a.dtype, np.number) and a.size > 0:
                            df_all[k] = a
                    except Exception:
                        continue
                if df_all:
                    df = pd.DataFrame(df_all)
                else:
                    raise RuntimeError("IBT loaded but no usable numeric channels were found.")
            else:
                raise RuntimeError(f"No known channels found in IBT (tried {', '.join(want)})")
        else:
            df = pd.DataFrame(data).dropna(how="all")

        # Normalize pedals to %
        for col in ("Throttle", "Brake"):
            if col in df.columns:
                try:
                    if float(np.nanmax(df[col].values)) <= 1.5:
                        df[col] = (df[col] * 100.0).clip(0, 100)
                except Exception:
                    pass

        # Synthesize Lap / LapDistPct if missing so charts don’t explode
        if "Lap" not in df.columns:
            df["Lap"] = 1
        if "LapDistPct" not in df.columns:
            if "LapDist" in df.columns and pd.to_numeric(df["LapDist"], errors="coerce").fillna(0).max() > 0:
                df["Lap"] = df["Lap"].fillna(method="ffill").fillna(1).astype(int)
                max_per_lap = df.groupby("Lap")["LapDist"].transform(lambda s: s.max() if s.max() != 0 else 1.0)
                df["LapDistPct"] = df["LapDist"] / max_per_lap
            else:
                if "Lap" not in df.columns:
                    df["Lap"] = 1
                df["_idx"] = df.groupby("Lap").cumcount()
                max_idx = df.groupby("Lap")["_idx"].transform(lambda s: s.max() if s.max() != 0 else 1)
                df["LapDistPct"] = df["_idx"] / max_idx
                df.drop(columns=["_idx"], inplace=True)

        return df

    except Exception as e:
        raise RuntimeError(f"IBT parse error: {e}") from e
    finally:
        try:
            if ibt is not None and hasattr(ibt, "close"):
                ibt.close()
        except Exception:
            pass
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def tolerant_load_csv(file_bytes: bytes) -> pd.DataFrame:
    """Try common encodings + delimiters for CSV."""
    for enc in ("utf-8", "latin-1"):
        for sep in (",", ";", "\t", "|"):
            try:
                return pd.read_csv(io.BytesIO(file_bytes), encoding=enc, sep=sep)
            except Exception:
                continue
    raise RuntimeError("Could not parse CSV with common encodings/separators.")


def stash_df(df: pd.DataFrame):
    st.session_state["telemetry_df"] = df
    st.session_state["telemetry_columns"] = list(df.columns)


def get_tracks():
    # If your main app injects tracks into session_state, we’ll use that.
    if "tracks" in st.session_state and isinstance(st.session_state["tracks"], dict) and st.session_state["tracks"]:
        return st.session_state["tracks"]
    # Fallback so this page works solo
    return {
        "Watkins Glen International (Cup)": {},
        "Richmond Raceway": {},
        "Daytona International Speedway": {},
    }

# =========================
# UI
# =========================

st.title("Telemetry Viewer")

tracks = get_tracks()
track_names = sorted(list(tracks.keys())) if tracks else ["Unknown Track"]
default_idx = track_names.index("Watkins Glen International (Cup)") if "Watkins Glen International (Cup)" in track_names else 0

tab_track, tab_run, tab_charts = st.tabs(["Track", "Run type", "Charts"])

with tab_track:
    track_pick = st.selectbox("Track", track_names, index=default_idx, key="track_pick")

with tab_run:
    run_type = st.radio("Run type", ["Practice", "Qualifying", "Race"], index=0, horizontal=True, key="run_type")

    # >>> Uploader lives right under Run type <<<
    up = st.file_uploader("Upload telemetry (.csv or .ibt)", type=["csv", "ibt"], key="up_file")
    if up is not None:
        suffix = Path(up.name).suffix.lower()
        try:
            raw = up.read()
            if suffix == ".ibt":
                df = tolerant_load_ibt(raw)
            else:
                df = tolerant_load_csv(raw)

            # light normalization
            if "Speed" in df.columns:
                df["Speed"] = pd.to_numeric(df["Speed"], errors="coerce")

            stash_df(df)
            st.success(f"Loaded {up.name} with {df.shape[0]} rows and {df.shape[1]} columns.")
        except Exception as e:
            st.error(str(e))

with tab_charts:
    st.subheader("Channels and File info")
    if "telemetry_df" not in st.session_state:
        st.info("No file loaded yet. Go to the 'Run type' tab and upload a .csv or .ibt telemetry file.")
    else:
        df = st.session_state["telemetry_df"]
        cols = st.session_state.get("telemetry_columns", list(df.columns))

        # Metadata
        st.markdown(f"**Columns:** {', '.join(map(str, cols))}")
        st.write(f"**Rows:** {len(df)}")

        # Peek
        st.dataframe(df.head(100))

        # Simple default chart(s)
        try:
            if "LapDistPct" in df.columns and "Speed" in df.columns:
                st.line_chart(df[["LapDistPct", "Speed"]].set_index("LapDistPct"))
            elif "Speed" in df.columns:
                st.line_chart(df["Speed"])
        except Exception:
            pass

st.caption("Uploader is under the 'Run type' tab. IBT loader falls back to any numeric channels if the usual ones aren't found.")
