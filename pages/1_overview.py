"""Overview: headline cards, the linked map and time chart, the rare-event panel and the finding of the week."""
from datetime import date

import pandas as pd
import streamlit as st

from src import charts, config, ui
from src import pipeline as P
from src.findings import compute_findings

CODE_TO_NAME = {code: name for code, _, name, *_ in config.PROVINCES}
ALL = "All Cambodia"

st.title("Where and when are road crashes reported in Cambodia?")
st.markdown(
    "**Question.** Where and when do the road crashes reported in Khmer-language news cluster, how much of the real burden "
    "does that coverage capture, and how does Cambodia's road death rate compare with ASEAN?  \n"
    "**Hypotheses.** H1: crashes reported outside Phnom Penh are more often fatal, and the capital is over-reported for its "
    "population. H2: Cambodia's road death rate rose between 2000 and 2019 while most ASEAN members' fell.")
ui.disclaimer()

# ---------------- Left panel ----------------
ui.add_data_panel()
ui.sources_panel()
st.sidebar.subheader("Filters")
include_uploads = st.sidebar.toggle("Include uploaded rows", value=True)
crashes = ui.crashes(include_uploads)
census, worldbank, geojson = ui.census(), ui.worldbank(), ui.boundaries()
start_year, end_year = st.sidebar.slider("Period (re-colours the map)", 2018, 2024, (2018, 2024))
map_measure = st.sidebar.radio("Map measure", list(P.MAP_MEASURES), format_func=P.MAP_MEASURES.get)
series_measure = st.sidebar.radio("Time chart measure", list(P.SERIES_MEASURES), format_func=P.SERIES_MEASURES.get)
st.session_state.setdefault("province", ALL)
st.sidebar.selectbox("Place (or click the map)", [ALL] + sorted(CODE_TO_NAME.values()), key="province")
province = None if st.session_state.province == ALL else st.session_state.province


def _on_map_select():
    """Clicking a province filters the time chart; clicking it again returns to all of Cambodia."""
    state = st.session_state.get("province_map")
    points = state.selection.points if state and state.selection else []
    if not points:
        return
    location = points[0].get("location")
    try:
        name = CODE_TO_NAME.get(int(location))
    except (TypeError, ValueError):
        return
    if name:
        st.session_state.province = ALL if st.session_state.province == name else name


# ---------------- Headline cards ----------------
period = crashes[crashes.year.between(start_year, end_year)]
panel = P.province_panel(period, census, worldbank, start_year, end_year)
scope = period if province is None else period[period.province == province]
scope_panel = panel if province is None else panel[panel.province == province]
person_years = scope_panel.person_years.sum()
capital_test = P.test_capital_vs_rest(period)
asean = P.test_asean_trend(worldbank)
place = province or "Cambodia"

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Crashes reported, {place}", f"{len(scope):,}", help=f"Distinct crashes in news reports, {start_year}-{end_year}.")
c2.metric("Deaths per 100k a year", f"{scope.deaths.sum() / person_years * 1e5:.2f}",
          help="Reported deaths per 100,000 residents per year: news deaths divided by census 2019 population moved to each year with national growth.")
c3.metric("Fatal share: provinces vs capital", f"{capital_test['fatal_share_outside']:.0%} vs {capital_test['fatal_share_inside']:.0%}",
          help="Share of reported crashes with known severity that were fatal (whole country, selected period).")
c4.metric(f"WHO road deaths per 100k, {asean['year']}", f"{asean['khm_rate']:.1f}",
          f"{asean['khm_change']:+.1f} since 2000 · rank {asean['khm_rank']} of {asean['members']} in ASEAN", delta_color="inverse",
          help="World Bank SH.STA.TRAF.P5, a WHO modelled estimate. Rank 1 = highest rate.")

# ---------------- Map and time chart ----------------
left, right = st.columns([1, 1], gap="medium")
with left:
    fig_map, edges = charts.province_map(panel, map_measure, geojson, province,
                                         title=f"{P.MAP_MEASURES[map_measure]}, {start_year}-{end_year}")
    for trace in fig_map.data:
        trace.update(selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)))
    st.plotly_chart(fig_map, key="province_map", on_select=_on_map_select, selection_mode="points",
                    config={"displayModeBar": False, "scrollZoom": False})
    st.caption(f"Class breaks (quantiles): {', '.join(f'{e:g}' for e in edges)}. Grey: fewer than 10 reports, so a share "
               "would mostly be noise. Boundaries and population: ODC census 2019 (CC BY-SA).")

with right:
    series = P.monthly_series(crashes, series_measure, province)
    is_count = series_measure in ("reports", "deaths")
    forecast = P.forecast_vs_naive(series) if is_count else None
    decomposition = P.decompose(series) if is_count and series.sum() > 0 else None
    outliers = P.robust_outliers(series) if is_count else None
    if forecast and forecast.get("ok"):
        verdict = "beats" if forecast["beats_naive"] else "does not beat"
        title = (f"{P.SERIES_MEASURES[series_measure]}, {place}<br><sup>The forecast {verdict} 'same month last year' "
                 f"on {config.TEST_YEAR} (mean absolute error {forecast['mae_model']:.1f} vs {forecast['mae_naive']:.1f})</sup>")
    elif is_count:
        title = f"{P.SERIES_MEASURES[series_measure]}, {place}<br><sup>Too few months with reports to forecast</sup>"
    else:
        title = f"{P.SERIES_MEASURES[series_measure]}, {place}"
    st.plotly_chart(charts.time_chart(series, decomposition, forecast, outliers, title,
                                      highlight=(f"{start_year}-01-01", f"{end_year}-12-31")),
                    config={"displayModeBar": False})
    if forecast and forecast.get("ok"):
        m1, m2, m3 = st.columns(3)
        m1.metric(f"Model error, {config.TEST_YEAR}", f"{forecast['mae_model']:.1f}", help="Mean absolute error per month.")
        m2.metric("Naive error", f"{forecast['mae_naive']:.1f}")
        m3.metric("MASE", f"{forecast['mase_model']:.2f}", help="Below 1 beats the in-sample seasonal naive error.")
    elif not is_count:
        st.caption("Forecasts are drawn for counts only; a share bounded by 0 and 100 needs a different model.")
    elif forecast:
        st.caption(forecast["reason"])

# ---------------- Detail tabs ----------------
tab_season, tab_rare, tab_asean, tab_table = st.tabs(
    ["Trend, season and change on a year earlier", "Rare-event panel", "Cambodia vs ASEAN", "Province table"])

with tab_season:
    if decomposition is not None:
        yoy = P.year_on_year(series).dropna()
        a, b = st.columns(2)
        peak = decomposition.seasonal_factor.groupby(decomposition.index.month).mean()
        a.plotly_chart(charts.seasonal_chart(decomposition, f"Seasonal peak in {pd.Timestamp(2000, int(peak.idxmax()), 1):%B} (x{peak.max():.1f}): "
                                             "the months articles were collected"),
                       config={"displayModeBar": False})
        b.plotly_chart(charts.yoy_chart(yoy, f"Change on the same month a year earlier: {(yoy > 0).mean():.0%} of months up"),
                       config={"displayModeBar": False})
        flagged = outliers[outliers.flagged] if outliers is not None else pd.DataFrame()
        st.markdown(f"**Flagged months** (modified z-score above 3.5; flagged, not removed): "
                    + (", ".join(f"{i:%b %Y} ({v:.0f})" for i, v in flagged.value.items()) or "none"))
    else:
        st.info("Choose a count measure (reported crashes or deaths) to see trend and season.")

with tab_rare:
    results, cases, costs = ui.rare_event()
    st.markdown(f"**Task.** {results['target']}. Trained on {results['train_years']} ({results['train_rows']} crashes), "
                f"tested once on {results['test_year']} ({results['test_rows']} crashes). Model: {results['chosen']} "
                "(logistic regression in one scikit-learn pipeline).")
    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric(f"Base rate, {results['test_year']}", f"{results['base_rate_test']:.1%}", help=f"{results['positives_test']} multi-fatality crashes")
    r2.metric("Precision", f"{results['test_precision']:.2f}", help="Of flagged crashes, the share that were multi-fatality")
    r3.metric("Recall", f"{results['test_recall']:.2f}", help="Of multi-fatality crashes, the share flagged")
    r4.metric("Threshold", f"{results['threshold']:.2f}", help="Minimises 5 x misses + 1 x false alarms on training folds")
    r5.metric("Accuracy if never flagging", f"{results['accuracy_if_always_no']:.0%}",
              help=f"The model's accuracy is {results['test_accuracy']:.0%}: accuracy rewards ignoring the rare class.")
    a, b = st.columns([2, 3])
    a.plotly_chart(charts.cost_curve(costs, results["threshold"],
                                     f"A miss costs 5 false alarms, so the cheapest threshold is {results['threshold']:.2f}"),
                   config={"displayModeBar": False})
    shown = cases[cases.flagged == 1]
    if province:
        shown = shown[shown.province == province]
    b.markdown(f"**Crashes flagged in {results['test_year']}{' in ' + province if province else ''}** ({len(shown)})")
    b.dataframe(shown.drop(columns=["flagged", "event_id"]).sort_values("probability", ascending=False),
                hide_index=True, height=260, column_config={"incident_date": st.column_config.DateColumn("date")})
    st.warning(f"Fairness check: recall is {results['recall_other_provinces']:.0%} outside Phnom Penh and "
               f"{results['recall_phnom_penh']:.0%} inside it; the rule flags {results['flag_rate_phnom_penh']:.0%} of capital "
               f"crashes and {results['flag_rate_other']:.0%} elsewhere. It treats the two groups differently.")

with tab_asean:
    rates = worldbank.dropna(subset=["road_deaths_per_100k"])
    a, b = st.columns([1, 1])
    year = a.slider("Year", int(rates.year.min()), int(rates.year.max()), int(rates.year.max()), key="asean_year")
    asean_measure = a.radio("Measure", ["road_deaths_per_100k", "change_since_base"], horizontal=True,
                            format_func={"road_deaths_per_100k": "Deaths per 100,000",
                                         "change_since_base": f"Change since {int(rates.year.min())}"}.get)
    table = P.asean_table(worldbank, year, int(rates.year.min()))
    st.session_state.setdefault("asean_iso", "KHM")

    def _on_country():
        state = st.session_state.get("asean_map")
        points = state.selection.points if state and state.selection else []
        if points and points[0].get("location") in config.ASEAN:
            st.session_state.asean_iso = points[0]["location"]

    label = "Road deaths per 100,000" if asean_measure == "road_deaths_per_100k" else f"Change since {int(rates.year.min())}"
    fig = charts.asean_map(table, asean_measure, label, st.session_state.asean_iso)
    for trace in fig.data:
        trace.update(selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)))
    a.plotly_chart(fig, key="asean_map", on_select=_on_country, selection_mode="points", config={"displayModeBar": False})
    iso = st.session_state.asean_iso
    row = table.loc[iso]
    b.plotly_chart(charts.asean_paths(worldbank, iso, f"{row.country}: {row.road_deaths_per_100k:.1f} per 100,000 in {year}, "
                                                      f"rank {row['rank']} of {len(table)} (click a country)"),
                   config={"displayModeBar": False})
    trend = P.annual_trend_vs_naive(rates[rates.iso3 == iso].set_index("year").road_deaths_per_100k)
    b.caption(f"Forecast check on {trend['train_end'] + 1}-{trend['train_end'] + 5}: a linear trend fitted to earlier years has "
              f"MAE {trend['mae_trend']:.2f}; 'same as last year' has {trend['mae_naive']:.2f}. WHO estimates are modelled, "
              "not counted, and their quality differs between countries.")

with tab_table:
    show = panel[["province", "reports", "deaths", "population_2019", "reports_per_100k_yr", "deaths_per_100k_yr",
                  "fatal_share_pct", "report_share_pct", "population_share_pct"]].sort_values("reports_per_100k_yr", ascending=False)
    st.dataframe(show.round(2), hide_index=True, height=420)


# ---------------- Finding of the week ----------------
@st.cache_data(show_spinner=False)
def _findings(data: pd.DataFrame):
    return compute_findings(data, ui.census(), ui.worldbank(), ui.official())


found = _findings(crashes)
st.subheader("Finding of the week")
if found:
    pick = found[date.today().isocalendar().week % len(found)]
    st.markdown(f"### {pick.number}\n{pick.sentence}\n\n*What it does not prove:* {pick.caveat}")
else:
    st.caption("No finding can be computed from the current data.")
st.page_link("pages/4_findings.py", label="All findings with their charts", icon="📌")
