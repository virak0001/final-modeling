"""Streamlit helpers: cached loaders, the automatic-sources panel and shared page parts."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from src import config, fetch
from src import pipeline as P
from src.validate import load_uploads

REFRESH_COOLDOWN = timedelta(minutes=15)  # protects the upstream APIs from repeated clicks


def _mtime(path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


@st.cache_data(show_spinner=False)
def _public(_stamp: float) -> pd.DataFrame:
    return P.load_public_crashes()


@st.cache_data(show_spinner=False)
def _uploads(_stamp: float) -> pd.DataFrame:
    return load_uploads()


@st.cache_data(show_spinner=False)
def census() -> pd.DataFrame:
    return P.load_census()


@st.cache_data(show_spinner=False)
def boundaries() -> dict:
    return P.load_boundaries()


@st.cache_data(show_spinner=False)
def worldbank() -> pd.DataFrame:
    return P.load_worldbank()


@st.cache_data(show_spinner=False)
def official() -> pd.DataFrame:
    return P.load_official()


@st.cache_data(show_spinner=False)
def rare_event() -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    results = json.loads(config.RARE_EVENT_JSON.read_text(encoding="utf-8"))
    cases = pd.read_csv(config.RARE_EVENT_CASES, parse_dates=["incident_date"])
    costs = pd.read_csv(config.RARE_EVENT_COSTS)
    return results, cases, costs


def crashes(include_uploads: bool = True) -> pd.DataFrame:
    public = _public(_mtime(config.CRASHES_PUBLIC))
    uploads = _uploads(_mtime(config.UPLOAD_LOG)) if include_uploads else None
    return _prepared(public, uploads)


@st.cache_data(show_spinner=False)
def _prepared(public: pd.DataFrame, uploads: pd.DataFrame | None) -> pd.DataFrame:
    return P.prepare_crashes(public, uploads)


def last_pulls() -> pd.DataFrame:
    log = fetch.read_fetch_log()
    if log.empty:
        return log
    log["retrieved_at_utc"] = pd.to_datetime(log.retrieved_at_utc, utc=True)
    return log.sort_values("retrieved_at_utc").groupby("source").tail(1).sort_values("source")


def refresh_now() -> list[dict]:
    """Pull every automatic source, rebuild the reference tables, clear caches."""
    results = fetch.fetch_all()
    census_table, geo = P.build_census_and_boundaries()
    census_table.to_csv(config.CENSUS_CSV, index=False, encoding="utf-8")
    config.PROVINCE_GEOJSON.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    P.build_worldbank().to_csv(config.WORLDBANK_CSV, index=False)
    st.cache_data.clear()
    return results


def sources_panel() -> None:
    """Left panel: each automatic source, whether the last pull worked, when it ran, and a refresh button."""
    st.sidebar.subheader("Automatic sources")
    pulls = last_pulls()
    if pulls.empty:
        st.sidebar.caption("No pulls logged yet.")
    for row in pulls.itertuples():
        icon = "✅" if row.status == "ok" else "⚠️"
        st.sidebar.caption(f"{icon} **{row.source}** · {row.status} · {row.retrieved_at_utc:%Y-%m-%d %H:%M} UTC · {row.rows} rows")
    newest = pulls.retrieved_at_utc.max() if len(pulls) else None
    cooling = newest is not None and datetime.now(timezone.utc) - newest.to_pydatetime() < REFRESH_COOLDOWN
    if st.sidebar.button("Refresh now", disabled=bool(cooling),
                         help="Pulls World Bank and ODC again. Limited to once every 15 minutes." if not cooling
                         else "Pulled less than 15 minutes ago."):
        with st.spinner("Pulling sources..."):
            results = refresh_now()
        failed = [r["source"] for r in results if r["status"] != "ok"]
        # The message is kept in session state because st.rerun() would otherwise wipe it before anyone reads it.
        st.session_state["refresh_message"] = (("warning", f"Failed: {', '.join(failed)}. Earlier data kept.") if failed
                                               else ("success", "All sources refreshed."))
        st.rerun()
    message = st.session_state.pop("refresh_message", None)
    if message:
        getattr(st.sidebar, message[0])(message[1])
    st.sidebar.caption("A GitHub Actions job also pulls every Monday (.github/workflows/fetch.yml).")


def add_data_panel() -> None:
    st.sidebar.subheader("Add data")
    st.sidebar.page_link("pages/2_upload.py", label="Upload a CSV or Excel file", icon="📤")
    log = config.UPLOAD_LOG
    if log.exists():
        last = pd.read_csv(log).tail(1)
        if len(last):
            r = last.iloc[0]
            st.sidebar.caption(f"Last upload: {r.file_name} · {r.rows_accepted} accepted, {r.rows_rejected} rejected")


def disclaimer() -> None:
    st.caption("Reported crashes are crashes that Khmer-language news chose to cover. They show coverage as much as risk. "
               "Article text is not published: only fields extracted from it.")
