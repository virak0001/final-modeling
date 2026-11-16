"""Data quality: every source with its licence, retrieval date, missing share and flagged outliers; the logs."""
import json

import pandas as pd
import streamlit as st

from src import charts, config, ui
from src import pipeline as P
from src.names import province_table

st.title("Data quality")
st.markdown("Every source, its licence, when it was retrieved, how much is missing, and what was flagged. "
            "Nothing flagged was deleted.")

crashes, census, worldbank, official = ui.crashes(True), ui.census(), ui.worldbank(), ui.official()
pulls = ui.last_pulls()


def retrieved(prefix: str) -> str:
    rows = pulls[pulls.source.str.startswith(prefix) & (pulls.status == "ok")] if len(pulls) else pulls
    return f"{rows.retrieved_at_utc.max():%Y-%m-%d %H:%M} UTC" if len(rows) else "not yet pulled"


meta_path = config.RAW / "odc" / f"{config.ODC_CENSUS_PACKAGE}.meta.json"
census_meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
series = P.monthly_series(crashes)
spikes = P.robust_outliers(series)
fatal = crashes[crashes.deaths > 0]
d_low, d_high = P.iqr_fences(fatal.deaths)
injured = crashes[crashes.injuries_total > 0]
i_low, i_high = P.iqr_fences(injured.injuries_total)
density_z = P.robust_outliers(census.set_index("province").density_per_km2)
rates = worldbank.pivot(index="iso3", columns="year", values="road_deaths_per_100k")
latest = worldbank.dropna(subset=["road_deaths_per_100k"]).year.max()
rate_z = P.robust_outliers(rates[latest])
news_missing = {"incident_date": crashes.incident_date.isna().mean(), "province": crashes.province.isna().mean(),
                "severity": (crashes.severity == "Not stated").mean(), "time_of_day": (crashes.time_of_day == "Unknown").mean()}

sources = pd.DataFrame([
    {"source": "Khmer news crash reports (team dataset)", "provider": "Khmer-language news sites, collected by the team",
     "licence": "No licence: article text is copyright of each outlet (85 rows carry a no-copying notice, 71 a VOD/CCIM footer). "
                "Text withheld; only extracted fields are published.",
     "retrieved": "Collected before 2026-11-01; uploads appended", "access": "Upload page / src/extract_accidents.py",
     "rows": len(crashes),
     "missing": "; ".join(f"{k} {v:.0%}" for k, v in news_missing.items()),
     "outliers flagged": f"{int(spikes.flagged.sum())} spike months (|robust z| > 3.5); {int((fatal.deaths > d_high).sum())} crashes with "
                         f"more than {d_high:g} deaths and {int((injured.injuries_total > i_high).sum())} with more than {i_high:g} injured (3 x IQR fences)"},
    {"source": "Population census 2019, final totals by province (with boundaries)", "provider": "NIS via Open Development Cambodia",
     "licence": f"{census_meta.get('license_title', 'CC BY-SA')} ({census_meta.get('license_id', 'cc-by-sa')})",
     "retrieved": retrieved("ODC GeoServer"), "access": "ODC GeoServer WFS + CKAN API", "rows": len(census),
     "missing": f"{census.isna().mean().mean():.0%} of cells",
     "outliers flagged": ", ".join(f"{p} density {census.set_index('province').density_per_km2[p]:,.0f}/km2"
                                   for p in density_z.index[density_z.flagged]) or "none"},
    {"source": "World Development Indicators (road mortality, population, urban share, GDP per head)", "provider": "World Bank",
     "licence": "CC BY 4.0", "retrieved": retrieved("World Bank"), "access": "api.worldbank.org/v2", "rows": len(worldbank),
     "missing": f"road deaths per 100k: {worldbank.road_deaths_per_100k.isna().mean():.0%} of country-years "
                f"(the WHO series covers 2000-{latest} only)",
     "outliers flagged": ", ".join(f"{i} {rates.loc[i, latest]:.1f}" for i in rate_z.index[rate_z.flagged]) or f"none in {latest}"},
    {"source": f"Official national totals (crashes, deaths, injured), {int(official.year.min())}-{int(official.year.max())}",
     "provider": "National Road Safety Committee (NRSC) annual figures, as released by the Ministry of Public Works and Transport, "
                 "the AKP state news agency and national news",
     "licence": "Government statistics in public releases; no licence stated. The committee's report is not online, so each year "
                "is typed in from the page named in official_totals.csv (source_url, source_date)",
     "retrieved": f"Checked {official.retrieved.max()}" if "retrieved" in official else "Entered by hand",
     "access": "data/reference/official_totals.csv", "rows": len(official),
     "missing": f"{official[['official_deaths', 'official_crashes']].isna().mean().mean():.0%} of year-measures; "
                f"serious/minor split missing for {int(official.official_injured_minor.isna().sum()) if 'official_injured_minor' in official else len(official)} of {len(official)} years",
     "outliers flagged": "-"},
])
st.subheader("Sources and licences")
st.dataframe(sources[["source", "provider", "licence", "retrieved", "access", "rows"]], hide_index=True, width="stretch",
             row_height=90)
st.subheader("Missing values and outliers by source")
st.dataframe(sources[["source", "missing", "outliers flagged"]], hide_index=True, width="stretch", row_height=70,
             column_config={"outliers flagged": st.column_config.TextColumn(width="large")})

st.subheader("Why the gaps exist")
st.markdown(
    f"- **Province ({news_missing['province']:.0%} missing):** some articles name only a road or a district that the extractor "
    "could not place. Left blank and excluded from the map, never guessed.\n"
    f"- **Severity ({news_missing['severity']:.0%} 'Not stated'):** some articles report a crash without saying whether anyone was hurt. "
    "Excluded from fatal shares and from the rare-event task.\n"
    f"- **Time of day ({news_missing['time_of_day']:.0%} unknown):** many articles give no time, or an hour without morning/evening. "
    "Kept as an 'Unknown' category instead of filled, because guessing would invent night crashes.\n"
    "- **WHO road mortality after the last year:** the estimate is published every few years; there is nothing to fill.\n"
    f"- **Official totals:** the National Road Safety Committee series starts in {int(official.year.min())} on the pages found; the news "
    "sample starts in 2018, so 2018 and 2019 have no official comparison. The gap is shown, not filled.")

a, b = st.columns(2)
cols = ["incident_date", "province", "severity", "time_of_day", "road_type", "road_name", "collision_type", "stated_factors"]
known = crashes.dropna(subset=["year"])
missing_map = P.missingness_by_year(known[known.year.between(2016, 2024)], cols)
a.plotly_chart(charts.missingness_heatmap(missing_map, "Missingness map, news crashes: road names and factors are mostly absent"),
               config={"displayModeBar": False})
wb_missing = worldbank.pivot(index="country", columns="year", values="road_deaths_per_100k").isna().mul(100)
b.plotly_chart(charts.missingness_heatmap(wb_missing, "Missingness map, World Bank road mortality: only 2000 onwards"),
               config={"displayModeBar": False})
assumed = crashes.casualty_note.fillna("").str.contains("assumed 1")
st.caption("Missing includes 'Unknown', 'Not stated' and 'Unclassified'. Categorical gaps are kept as their own category, not filled. "
           f"The one imputation: {int(assumed.sum())} fatal crashes say someone died without a number; deaths was set to 1 "
           f"(before: blank; after: 1). That adds {int(assumed.sum())} of {int(crashes.deaths.sum()):,} reported deaths, "
           "a lower bound.")

fill = P.imputation_before_after(crashes)
st.plotly_chart(charts.before_after_chart(
    fill, f"Before and after the one fill on the same axes: {fill.attrs['filled']} fatal crashes with no death count became 1"),
    config={"displayModeBar": False})

st.subheader("Joins (row counts before and after)")
st.dataframe(pd.read_csv(config.JOIN_LOG), hide_index=True, width="stretch")
st.subheader("Name-matching table (province code is the join key)")
st.dataframe(province_table(), hide_index=True, width="stretch")

st.subheader("Automatic pulls")
st.dataframe(ui.fetch.read_fetch_log().iloc[::-1], hide_index=True, width="stretch", height=260)
st.subheader("Uploads")
if config.UPLOAD_LOG.exists():
    log = pd.read_csv(config.UPLOAD_LOG)
    last = log.iloc[-1]
    st.markdown(f"Last upload: **{last.file_name}** on {last.uploaded_at_utc}: {last.rows_accepted} rows stored, "
                f"{last.rows_rejected} rejected.")
    rejected = config.UPLOADS / f"{last.uploaded_at_utc}_{last.file_name.rsplit('.', 1)[0]}.rejected.csv"
    if rejected.exists():
        st.dataframe(pd.read_csv(rejected), hide_index=True, width="stretch")
    st.dataframe(log.iloc[::-1], hide_index=True, width="stretch")
else:
    st.caption("No uploads yet.")

st.subheader("Official totals: the page behind each year")
st.dataframe(official[["year", "official_crashes", "official_deaths", "official_injured", "source_body", "source_url", "source_date", "verified"]],
             hide_index=True, width="stretch", column_config={"source_url": st.column_config.LinkColumn("source page")})
st.subheader("Data dictionary")
st.dataframe(pd.read_csv(config.DATA_DICTIONARY), hide_index=True, width="stretch", height=420)
