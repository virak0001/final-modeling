"""Upload page: check a CSV or Excel file of crash records, explain every rejected row, store the rest."""
import pandas as pd
import streamlit as st

from src import config, ui, validate

st.title("Upload crash records")
st.markdown(
    "Add crashes that the news sample missed, for example from a provincial police bulletin. One row is one crash. "
    "The file is checked before anything is stored; rejected rows are listed with every reason. "
    "Do not include names, ages, phone numbers or plate numbers in any column.")

with st.expander("Required format", expanded=True):
    st.markdown(
        f"- **Required columns:** {', '.join(f'`{c}`' for c in validate.REQUIRED)}\n"
        "- `incident_date`: a full date (day, month and year), preferably YYYY-MM-DD, between 2000-01-01 and today; "
        "a date with slashes such as 14/03/2024 is read as day/month/year\n"
        "- `province`: a province name in English or Khmer, or its official code (e.g. `KH-12` or `12`)\n"
        f"- `deaths`, `injuries_total`: **whole numbers of people for this one crash** (not rates or percentages); "
        f"at most {validate.MAX_DEATHS} and {validate.MAX_INJURIES}\n"
        f"- Optional: `severity` (must agree with the counts), `time_of_day` ({', '.join(config.TIME_OF_DAY)}), "
        f"`road_type` ({', '.join(config.ROAD_TYPES)}), `road_name`, `source`, and 0/1 flags such as `veh_motorcycle` or `factor_speeding`\n"
        f"- .csv or .xlsx, up to {validate.MAX_BYTES // 1024 // 1024} MB and {validate.MAX_ROWS:,} rows")
    template = pd.DataFrame([
        {"incident_date": "2024-03-14", "province": "Kampong Cham", "deaths": 1, "injuries_total": 2, "severity": "Fatal",
         "time_of_day": "Night (21-04)", "road_type": "National road", "road_name": "NR7", "source": "Provincial police",
         "veh_motorcycle": 1, "veh_heavy_truck": 1, "factor_speeding": 0},
        {"incident_date": "2024-03-20", "province": "តាកែវ", "deaths": 0, "injuries_total": 1, "severity": "",
         "time_of_day": "", "road_type": "", "road_name": "", "source": "", "veh_motorcycle": 1, "veh_heavy_truck": 0,
         "factor_speeding": 1},
    ])
    st.download_button("Download a template", template.to_csv(index=False).encode("utf-8-sig"), "crash_upload_template.csv",
                       "text/csv")

uploaded = st.file_uploader("Drag a CSV or Excel file here", type=["csv", "xlsx"], accept_multiple_files=False)
if uploaded is not None:
    try:
        frame = validate.read_upload(uploaded.name, uploaded.getvalue())
    except Exception as error:  # unreadable file: say why, store nothing
        st.error(f"The file could not be read: {error}")
        st.stop()
    result = validate.validate_crash_upload(frame, existing=validate.load_uploads())
    if result.file_errors:
        st.error("The whole file was rejected:\n\n" + "\n".join(f"- {e}" for e in result.file_errors))
        st.stop()
    for warning in result.warnings:
        st.warning(warning)
    a, b, c = st.columns(3)
    a.metric("Rows received", result.rows_received)
    b.metric("Rows accepted", len(result.accepted))
    c.metric("Rows rejected", len(result.rejected))
    if len(result.rejected):
        st.subheader("Rejected rows and why")
        st.dataframe(result.rejected, hide_index=True, width="stretch")
        st.download_button("Download the rejected rows", result.rejected.to_csv(index=False).encode("utf-8-sig"),
                           f"rejected_{validate.safe_filename(uploaded.name)}.csv", "text/csv")
    if len(result.accepted):
        st.subheader("Rows that passed")
        matches = validate.possible_matches(result.accepted, ui.crashes(False))
        if matches.any():
            st.warning(f"{int(matches.sum())} accepted row(s) match a crash already in the news sample on date, province "
                       "and casualties. They are stored if you continue, so that crash may then be counted twice.")
        st.dataframe(result.accepted.head(200), hide_index=True, width="stretch")
        if st.button(f"Store {len(result.accepted)} accepted rows", type="primary"):
            entry = validate.store_upload(result, uploaded.name)
            st.cache_data.clear()
            st.success(f"Stored as data/uploads/{entry['stored_as']} on {entry['uploaded_at_utc']}. "
                       f"The portal now includes these rows (the map and monthly chart cover {config.SERIES_START[:4]}-"
                       f"{config.SERIES_END[:4]}).")
    st.caption("On the free host the disk is reset when the app restarts. Uploads that should last are committed to the "
               "repository's data/uploads/ folder.")

st.subheader("Upload history")
if config.UPLOAD_LOG.exists():
    st.dataframe(pd.read_csv(config.UPLOAD_LOG).iloc[::-1], hide_index=True, width="stretch")
else:
    st.caption("No uploads yet.")
