"""Cleaning, joins, features and analysis shared by the portal (app.py) and the notebook.

Build every processed table from the raw files:   python -m src.pipeline
The raw news workbook contains copyrighted article text and is not in the public repository.
When it is absent, the step keeps the existing data/processed/crashes_public.csv and rebuilds everything else.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src import config
from src.names import code_for, match_province, province_table, write_matching_table

# --------------------------------------------------------------------------------------------
# Stage 1. Raw news workbook -> public crash table (no article text, no sub-province places)
# --------------------------------------------------------------------------------------------

# Dropped for copyright (article text and headlines) or for the small-area identification risk.
PRIVATE_COLUMNS = ["filename", "title", "Crash_Description", "fatality_evidence", "injury_evidence", "factor_evidence",
                   "district", "commune", "village", "km_marker", "incident_time", "duplicate_of"]


def build_public_crash_table(source=None, out=None) -> pd.DataFrame:
    source = source or config.RAW_NEWS_XLSX
    raw = pd.read_excel(source, sheet_name="Accidents")
    public = raw.drop(columns=[c for c in PRIVATE_COLUMNS if c in raw.columns])
    public.insert(0, "origin", "news dataset")
    public.to_csv(out or config.CRASHES_PUBLIC, index=False, encoding="utf-8")
    return public


# --------------------------------------------------------------------------------------------
# Stage 2. Reference sources: census + boundaries, World Bank
# --------------------------------------------------------------------------------------------

def build_census_and_boundaries(raw_geojson=None, tolerance: float = 0.004) -> tuple[pd.DataFrame, dict]:
    """Split the ODC census layer into a census table and simplified province polygons, keyed on pro_code."""
    from shapely.geometry import mapping, shape

    raw_geojson = raw_geojson or json.loads((config.RAW / "odc" / "final_census2019_en.geojson").read_text(encoding="utf-8"))
    rows, features = [], []
    for feature in raw_geojson["features"]:
        p = feature["properties"]
        portal = match_province(p["provinces"]) or match_province(p.get("province_k"))
        code = int(p["pro_code"])
        rows.append({"pro_code": code, "province": portal, "name_census": p["provinces"], "name_khmer_census": p.get("province_k"),
                     "population_2019": int(p["total"]), "males": int(p["males"]), "females": int(p["females"]),
                     "households": int(p["households"]), "household_size": float(p["house_size"]),
                     "area_km2": float(p["area_km2"]), "density_per_km2": float(p["pop_km2"])})
        geometry = shape(feature["geometry"]).simplify(tolerance, preserve_topology=True)
        geo = json.loads(json.dumps(mapping(geometry)), parse_float=lambda x: round(float(x), 4))
        features.append({"type": "Feature", "id": code, "properties": {"pro_code": code, "province": portal}, "geometry": geo})
    census = pd.DataFrame(rows).sort_values("pro_code").reset_index(drop=True)
    by_code = {code: portal for code, _, portal, *_ in config.PROVINCES}
    mismatched = census[census.province != census.pro_code.map(by_code)]
    if len(mismatched):
        raise ValueError(f"Census names do not match codes: {mismatched[['pro_code', 'name_census']].to_dict('records')}")
    boundaries = {"type": "FeatureCollection", "features": sorted(features, key=lambda f: f["id"])}
    return census, boundaries


def build_worldbank() -> pd.DataFrame:
    """Wide table: one row per ASEAN country-year with every fetched indicator."""
    frames = []
    for code, name in config.WORLDBANK_INDICATORS.items():
        path = config.RAW / "worldbank" / f"{code}.json"
        if not path.exists():
            continue
        from src.fetch import parse_worldbank
        pages = json.loads(path.read_text(encoding="utf-8"))
        part = pd.concat([parse_worldbank(page, code) for page in pages])
        frames.append(part.assign(indicator=name))
    long = pd.concat(frames, ignore_index=True)
    wide = long.pivot_table(index=["iso3", "year"], columns="indicator", values="value", aggfunc="first").reset_index()
    wide.insert(1, "country", wide.iso3.map(config.ASEAN))
    return wide.sort_values(["iso3", "year"]).reset_index(drop=True)


# --------------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------------

def load_public_crashes(path=None) -> pd.DataFrame:
    return pd.read_csv(path or config.CRASHES_PUBLIC, parse_dates=["publish_date", "incident_date"], low_memory=False)


def load_census() -> pd.DataFrame:
    return pd.read_csv(config.CENSUS_CSV)


def load_boundaries() -> dict:
    return json.loads(config.PROVINCE_GEOJSON.read_text(encoding="utf-8"))


def load_worldbank() -> pd.DataFrame:
    return pd.read_csv(config.WORLDBANK_CSV)


def load_official() -> pd.DataFrame:
    return pd.read_csv(config.OFFICIAL_TOTALS)


def prepare_crashes(public: pd.DataFrame, uploads: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per distinct crash in Cambodia with original text (analysis_ready), plus uploaded rows."""
    crashes = public[public.analysis_ready == 1].copy()
    if uploads is not None and len(uploads):
        add = uploads.copy()
        add["origin"] = "upload: " + add.get("source_file", pd.Series("file", index=add.index)).astype(str)
        add["analysis_ready"] = 1
        add["event_id"] = "U" + pd.Series(range(len(add)), index=add.index).astype(str)
        add["incident_date_source"] = "Uploaded"
        add["province_confidence"] = "Uploaded"
        crashes = pd.concat([crashes, add], ignore_index=True)
    crashes["incident_date"] = pd.to_datetime(crashes.incident_date)
    crashes["year"] = crashes.incident_date.dt.year
    crashes["month"] = crashes.incident_date.dt.month
    crashes["period"] = crashes.incident_date.dt.to_period("M")
    crashes["pro_code"] = crashes.province.map(code_for)
    crashes["deaths"] = crashes.deaths.fillna(0)
    crashes["injuries_total"] = crashes.injuries_total.fillna(0)
    crashes["is_fatal"] = (crashes.severity == "Fatal").astype(int)
    crashes["severity_known"] = (crashes.severity != "Not stated").astype(int)
    flag_columns = [c for c in crashes.columns if c.startswith(("veh_", "factor_"))]
    crashes[flag_columns] = crashes[flag_columns].fillna(0).astype(int)
    for column, fill in (("time_of_day", "Unknown"), ("road_type", "Unknown"), ("severity", "Not stated")):
        crashes[column] = crashes[column].fillna(fill)
    return crashes


def load_crashes(include_uploads: bool = True) -> pd.DataFrame:
    from src.validate import load_uploads
    return prepare_crashes(load_public_crashes(), load_uploads() if include_uploads else None)


# --------------------------------------------------------------------------------------------
# Integration: province population by year, province panel
# --------------------------------------------------------------------------------------------

def province_population(census: pd.DataFrame, worldbank: pd.DataFrame, years) -> pd.DataFrame:
    """Census 2019 province totals moved to other years with the national growth from the World Bank.

    Claim: between 2018 and 2024 every province grew at the national rate. This is false in detail
    (Phnom Penh grew faster), so per-person rates for years far from 2019 carry extra error.
    """
    national = worldbank[worldbank.iso3 == "KHM"].set_index("year").population
    base = national.loc[2019]
    rows = [census[["pro_code", "province", "population_2019"]].assign(year=y, population=lambda d, y=y: d.population_2019
                                                                         * national.get(y, base) / base) for y in years]
    return pd.concat(rows, ignore_index=True)


def province_panel(crashes: pd.DataFrame, census: pd.DataFrame, worldbank: pd.DataFrame,
                   start_year: int, end_year: int, min_reports: int = 10) -> pd.DataFrame:
    """Per-province rates for a period. Counts are never mapped; rates per 100,000 person-years and shares are."""
    years = list(range(start_year, end_year + 1))
    period = crashes[crashes.year.between(start_year, end_year) & crashes.pro_code.notna()]
    grouped = period.groupby("pro_code").agg(
        reports=("event_id", "size"), deaths=("deaths", "sum"), fatal=("is_fatal", "sum"),
        severity_known=("severity_known", "sum"), national_road=("road_type", lambda s: (s == "National road").sum()),
        night=("time_of_day", lambda s: (s == "Night (21-04)").sum()), motorcycle=("veh_motorcycle", "sum"))
    person_years = province_population(census, worldbank, years).groupby("pro_code").population.sum().rename("person_years")
    panel = census.set_index("pro_code").join(grouped, how="left").join(person_years)
    counts = ["reports", "deaths", "fatal", "severity_known", "national_road", "night", "motorcycle"]
    panel[counts] = panel[counts].fillna(0).astype(int)
    panel["reports_per_100k_yr"] = panel.reports / panel.person_years * 1e5
    panel["deaths_per_100k_yr"] = panel.deaths / panel.person_years * 1e5
    enough = panel.severity_known >= min_reports
    panel["fatal_share_pct"] = np.where(enough, 100 * panel.fatal / panel.severity_known.where(enough), np.nan)
    panel["national_road_share_pct"] = np.where(panel.reports >= min_reports, 100 * panel.national_road / panel.reports.clip(lower=1), np.nan)
    panel["night_share_pct"] = np.where(panel.reports >= min_reports, 100 * panel.night / panel.reports.clip(lower=1), np.nan)
    panel["motorcycle_share_pct"] = np.where(panel.reports >= min_reports, 100 * panel.motorcycle / panel.reports.clip(lower=1), np.nan)
    panel["population_share_pct"] = 100 * panel.population_2019 / panel.population_2019.sum()
    panel["report_share_pct"] = 100 * panel.reports / max(panel.reports.sum(), 1)
    panel["low_sample"] = panel.reports < min_reports
    return panel.reset_index()


MAP_MEASURES = {
    "reports_per_100k_yr": "Reported crashes per 100,000 residents per year",
    "deaths_per_100k_yr": "Reported deaths per 100,000 residents per year",
    "fatal_share_pct": "Fatal share of reported crashes (%)",
}


def class_breaks(values, k: int = 5) -> list[float]:
    """Quantile class breaks, rounded and de-duplicated. Returns k+1 edges (fewer if values repeat)."""
    clean = pd.Series(values).dropna()
    if clean.empty:
        return [0.0, 1.0]
    edges = np.quantile(clean, np.linspace(0, 1, k + 1))
    decimals = 2 if clean.max() < 10 else 1
    edges = sorted(set(np.round(edges, decimals)))
    if len(edges) == 1:
        edges = [edges[0], edges[0] + 10 ** -decimals]
    return [float(e) for e in edges]


def assign_classes(values, edges) -> pd.Series:
    """Class index 0..k-1 for each value; NaN stays NaN."""
    values = pd.Series(values, dtype=float)
    idx = np.searchsorted(edges[1:-1], values, side="right").astype(float)
    idx[values.isna().to_numpy()] = np.nan
    return pd.Series(idx, index=values.index)


def class_labels(edges) -> list[str]:
    return [f"{a:g} to {b:g}" for a, b in zip(edges[:-1], edges[1:])]


# --------------------------------------------------------------------------------------------
# Time series
# --------------------------------------------------------------------------------------------

SERIES_MEASURES = {"reports": "Reported crashes per month", "deaths": "Reported deaths per month",
                   "fatal_share": "Fatal share of reported crashes (%), 3-month rolling"}


def monthly_series(crashes: pd.DataFrame, measure: str = "reports", province: str | None = None,
                   start: str = config.SERIES_START, end: str = config.SERIES_END) -> pd.Series:
    """Common frequency: every crash is placed in the month of its incident date; empty months count as 0."""
    data = crashes if province is None else crashes[crashes.province == province]
    index = pd.period_range(start, end, freq="M")
    if measure == "reports":
        series = data.groupby("period").size().reindex(index, fill_value=0).astype(float)
    elif measure == "deaths":
        series = data.groupby("period").deaths.sum().reindex(index, fill_value=0).astype(float)
    elif measure == "fatal_share":
        known = data[data.severity_known == 1].groupby("period").agg(f=("is_fatal", "sum"), n=("is_fatal", "size")).reindex(index, fill_value=0)
        rolled = known.rolling(3, min_periods=1).sum()
        series = (100 * rolled.f / rolled.n.where(rolled.n >= 5)).astype(float)
    else:
        raise ValueError(measure)
    series.index = index.to_timestamp()
    series.name = SERIES_MEASURES[measure]
    return series


def decompose(series: pd.Series, period: int = 12) -> pd.DataFrame:
    """STL on log(1+x): trend and season are separated multiplicatively, which suits counts with spikes."""
    from statsmodels.tsa.seasonal import STL

    filled = series.interpolate(limit_direction="both").fillna(0)
    fit = STL(np.log1p(filled), period=period, robust=True).fit()
    return pd.DataFrame({"observed": series, "trend": np.expm1(fit.trend), "seasonal_factor": np.exp(fit.seasonal),
                         "resid": fit.resid}, index=series.index)


def year_on_year(series: pd.Series) -> pd.Series:
    """Change on the same month a year earlier, in per cent. Undefined when last year's month was 0."""
    previous = series.shift(12)
    return (100 * (series - previous) / previous.where(previous > 0)).rename("Change on a year earlier (%)")


def robust_outliers(series: pd.Series, threshold: float = 3.5) -> pd.DataFrame:
    """Modified z-score (median and MAD). |z| > 3.5 is flagged, never removed."""
    values = series.dropna()
    median = values.median()
    mad = (values - median).abs().median()
    z = 0.6745 * (series - median) / (mad if mad > 0 else values.std() or 1)
    return pd.DataFrame({"value": series, "robust_z": z, "flagged": z.abs() > threshold})


def iqr_fences(values: pd.Series, k: float = 3.0) -> tuple[float, float]:
    q1, q3 = values.quantile([0.25, 0.75])
    return float(q1 - k * (q3 - q1)), float(q3 + k * (q3 - q1))


def _holt_winters(train: pd.Series, horizon: int):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    model = ExponentialSmoothing(np.log1p(train.clip(lower=0)), trend="add", damped_trend=True, seasonal="add",
                                 seasonal_periods=12, initialization_method="estimated").fit(optimized=True)
    log_forecast = model.forecast(horizon)
    sigma = float(np.std(model.resid, ddof=1))
    steps = np.sqrt(np.arange(1, horizon + 1))
    return (np.expm1(log_forecast).clip(lower=0), np.expm1(log_forecast - 1.2816 * sigma * steps).clip(lower=0),
            np.expm1(log_forecast + 1.2816 * sigma * steps))


def forecast_vs_naive(series: pd.Series, test_start: str = f"{config.TEST_YEAR}-01", horizon_ahead: int = 6) -> dict:
    """Split in time: fit up to test_start, score the held-out months once against a seasonal naive forecast,
    then refit on everything and forecast ahead. MASE < 1 means the model beats 'same month last year'."""
    series = series.astype(float)
    if series.isna().mean() > 0.2 or (series.fillna(0) > 0).sum() < 24:
        return {"ok": False, "reason": "Too few non-empty months to fit a seasonal model (need 24)."}
    series = series.interpolate(limit_direction="both")
    cut = pd.Timestamp(test_start)
    train, test = series[series.index < cut], series[series.index >= cut]
    point, low, high = _holt_winters(train, len(test))
    seasonal_naive = series.shift(12)[test.index]
    mae_model = float(np.mean(np.abs(test.values - point.values)))
    mae_naive = float(np.mean(np.abs(test.values - seasonal_naive.values)))
    in_sample_naive = float(np.mean(np.abs(train.diff(12).dropna())))
    future_index = pd.date_range(series.index[-1] + pd.offsets.MonthBegin(1), periods=horizon_ahead, freq="MS")
    f_point, f_low, f_high = _holt_winters(series, horizon_ahead)
    return {
        "ok": True, "train_end": str(train.index[-1].date()), "test_months": len(test),
        "test": pd.DataFrame({"actual": test.values, "model": point.values, "low80": low.values, "high80": high.values,
                              "seasonal_naive": seasonal_naive.values}, index=test.index),
        "ahead": pd.DataFrame({"model": f_point.values, "low80": f_low.values, "high80": f_high.values,
                               "seasonal_naive": series.reindex(future_index - pd.DateOffset(years=1)).values},
                              index=future_index),
        "mae_model": mae_model, "mae_naive": mae_naive,
        "mase_model": mae_model / in_sample_naive if in_sample_naive else np.nan,
        "mase_naive": mae_naive / in_sample_naive if in_sample_naive else np.nan,
        "beats_naive": mae_model < mae_naive,
    }


def annual_trend_vs_naive(values: pd.Series, holdout: int = 5) -> dict:
    """Annual WHO-modelled series: linear trend fitted on early years against 'same as last year'."""
    values = values.dropna().sort_index()
    train, test = values.iloc[:-holdout], values.iloc[-holdout:]
    slope, intercept = np.polyfit(train.index.astype(float), train.values, 1)
    trend = intercept + slope * test.index.astype(float)
    naive = np.repeat(train.iloc[-1], holdout)
    return {"train_end": int(train.index[-1]), "slope_per_year": float(slope),
            "mae_trend": float(np.mean(np.abs(test.values - trend))), "mae_naive": float(np.mean(np.abs(test.values - naive))),
            "test": pd.DataFrame({"actual": test.values, "trend": trend, "naive": naive}, index=test.index)}


# --------------------------------------------------------------------------------------------
# ASEAN comparison and hypothesis tests
# --------------------------------------------------------------------------------------------

def asean_table(worldbank: pd.DataFrame, year: int | None = None, base_year: int = 2000) -> pd.DataFrame:
    rates = worldbank.dropna(subset=["road_deaths_per_100k"])
    year = year or int(rates.year.max())
    now = rates[rates.year == year].set_index("iso3")
    then = rates[rates.year == base_year].set_index("iso3")
    table = pd.DataFrame({"country": now.country, "road_deaths_per_100k": now.road_deaths_per_100k,
                          "change_since_base": now.road_deaths_per_100k - then.road_deaths_per_100k.reindex(now.index),
                          "gdp_per_capita_usd": now.get("gdp_per_capita_usd"), "urban_share_pct": now.get("urban_share_pct")})
    table["rank"] = table.road_deaths_per_100k.rank(ascending=False, method="min").astype(int)
    table.attrs.update(year=year, base_year=base_year)
    return table.sort_values("rank")


def test_capital_vs_rest(crashes: pd.DataFrame) -> dict:
    """H1a: crashes reported outside Phnom Penh are more often fatal. Two-proportion z-test, one-sided."""
    from scipy.stats import norm

    known = crashes[(crashes.severity_known == 1) & crashes.province.notna()]
    inside = known[known.province == "Phnom Penh"].is_fatal
    outside = known[known.province != "Phnom Penh"].is_fatal
    p1, p2, n1, n2 = outside.mean(), inside.mean(), len(outside), len(inside)
    pooled = (outside.sum() + inside.sum()) / (n1 + n2)
    z = (p1 - p2) / np.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    return {"fatal_share_outside": p1, "fatal_share_inside": p2, "n_outside": n1, "n_inside": n2, "z": float(z),
            "p_value_one_sided": float(1 - norm.cdf(z)), "ratio": p1 / p2 if p2 else np.nan}


def test_coverage_vs_population(panel: pd.DataFrame) -> dict:
    """H1b: reports are spread like the population. Chi-square goodness of fit; rejecting it means coverage bias."""
    from scipy.stats import chisquare, spearmanr

    observed = panel.reports.to_numpy()
    expected = panel.population_2019.to_numpy() / panel.population_2019.sum() * observed.sum()
    chi2, p = chisquare(observed, expected)
    rho, rho_p = spearmanr(panel.density_per_km2, panel.reports_per_100k_yr)
    capital = panel.set_index("province").loc["Phnom Penh"]
    rest = panel[panel.province != "Phnom Penh"]
    rest_rate = rest.reports.sum() / rest.person_years.sum() * 1e5
    return {"chi2": float(chi2), "p_value": float(p), "capital_report_share": float(capital.report_share_pct),
            "capital_population_share": float(capital.population_share_pct),
            "capital_rate": float(capital.reports_per_100k_yr), "rest_rate": float(rest_rate),
            "rate_ratio": float(capital.reports_per_100k_yr / rest_rate) if rest_rate else np.nan,
            "spearman_density_rate": float(rho), "spearman_p": float(rho_p)}


def test_asean_trend(worldbank: pd.DataFrame, start: int = 2000, end: int | None = None) -> dict:
    """H2: Cambodia's modelled road death rate rose while most ASEAN members' fell."""
    table = asean_table(worldbank, end, start)
    others = table.drop(index="KHM")
    return {"year": table.attrs["year"], "khm_change": float(table.loc["KHM", "change_since_base"]),
            "khm_rate": float(table.loc["KHM", "road_deaths_per_100k"]), "khm_rank": int(table.loc["KHM", "rank"]),
            "members": len(table), "others_fell": int((others.change_since_base < 0).sum()), "others": len(others)}


def coverage_vs_official(crashes: pd.DataFrame, official: pd.DataFrame, worldbank: pd.DataFrame) -> pd.DataFrame:
    """Annual join: news deaths and reports against official totals and the WHO-modelled estimate."""
    yearly = crashes.groupby("year").agg(news_reports=("event_id", "size"), news_deaths=("deaths", "sum"))
    khm = worldbank[worldbank.iso3 == "KHM"].set_index("year")
    modelled = (khm.road_deaths_per_100k * khm.population / 1e5).rename("who_modelled_deaths")
    table = official.set_index("year").join(yearly, how="left").join(modelled, how="left")
    table["news_share_of_official_deaths_pct"] = 100 * table.news_deaths / table.official_deaths
    table["news_share_of_official_crashes_pct"] = 100 * table.news_reports / table.official_crashes
    return table


# --------------------------------------------------------------------------------------------
# Week 8: feature selection (a correlation rule) and PCA across province indicators
# --------------------------------------------------------------------------------------------

# Ordered by completeness: when two indicators are redundant, the one listed later is dropped. Reports per
# 100,000 come first because every located crash counts; deaths need the article to state a number.
PCA_INDICATORS = ["reports_per_100k_yr", "deaths_per_100k_yr", "fatal_share_pct", "density_per_km2", "household_size",
                  "national_road_share_pct", "night_share_pct", "motorcycle_share_pct"]
CORRELATION_LIMIT = 0.8  # set before looking at the data


def select_indicators(corr: pd.DataFrame, limit: float = CORRELATION_LIMIT) -> tuple[list[str], list[dict]]:
    """Correlation rule: of any two indicators with |Spearman rho| >= limit, keep the one listed first."""
    kept, dropped = [], []
    for col in corr.columns:
        partner = next((k for k in kept if abs(corr.loc[col, k]) >= limit), None)
        if partner is None:
            kept.append(col)
        else:
            dropped.append({"dropped": col, "kept": partner, "rho": float(corr.loc[col, partner])})
    return kept, dropped


def province_pca(panel: pd.DataFrame, limit: float = CORRELATION_LIMIT) -> dict:
    """Spearman correlation across the indicators, the correlation rule, then PCA on what the rule keeps.
    The variance share before the rule is returned too, so the cost of the rule is visible."""
    from sklearn.decomposition import PCA
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    data = panel.dropna(subset=PCA_INDICATORS).set_index("province")[PCA_INDICATORS]
    corr = data.corr(method="spearman")
    kept, dropped = select_indicators(corr, limit)

    def fit(columns):
        pipe = make_pipeline(StandardScaler(), PCA(n_components=min(3, len(columns)), random_state=config.RANDOM_STATE))
        scores = pipe.fit_transform(data[columns])
        return pipe.named_steps["pca"], scores

    pca, scores = fit(kept)
    pca_all, _ = fit(PCA_INDICATORS)
    loadings = pd.DataFrame(pca.components_.T, index=kept, columns=[f"PC{i + 1}" for i in range(pca.n_components_)])
    return {"provinces": len(data), "correlation": corr, "limit": limit, "kept": kept, "dropped": dropped,
            "variance_share": pca.explained_variance_ratio_, "variance_share_all": pca_all.explained_variance_ratio_,
            "loadings": loadings, "index": pd.Series(scores[:, 0], index=data.index, name="PC1 index")}


# --------------------------------------------------------------------------------------------
# Week 10 and 13: rare-event task in one pipeline
# --------------------------------------------------------------------------------------------

RARE_CATEGORICAL = ["time_of_day", "day_type", "season", "province_group", "road_type"]
COLLISIONS = {"rollover": "Rollover", "rear_end": "Rear-end", "head_on": "Head-on", "side": "Side/sideswipe",
              "ran_off_road": "Ran off road", "fixed_object": "Hit fixed object", "pedestrian": "Hit pedestrian"}
COST_MISS, COST_FALSE_ALARM = 5.0, 1.0


def rare_event_frame(crashes: pd.DataFrame) -> pd.DataFrame:
    """Target: a crash with two or more deaths. Features describe circumstances, never the outcome.

    Claims behind the features: buses and trucks carry or hit more people (veh_*); national roads and
    expressways mean higher speeds (road_type); nights and weekends change traffic and drinking (time, day_type);
    the rainy season makes roads slippery (season); more vehicle types means a bigger crash (n_vehicle_types).
    """
    data = crashes[(crashes.severity_known == 1) & crashes.year.between(2018, config.TEST_YEAR)
                   & crashes.origin.eq("news dataset")].copy()
    data["multi_fatal"] = (data.deaths >= 2).astype(int)
    weekday = data.incident_date.dt.day_of_week
    data["day_type"] = np.where(weekday >= 5, "Weekend", "Weekday")
    data["season"] = np.where(data.month.between(5, 10), "Rainy (May-Oct)", "Dry (Nov-Apr)")
    collision = data.collision_type.fillna("")
    for name, label in COLLISIONS.items():
        data[f"col_{name}"] = collision.str.contains(label, regex=False).astype(int)
    data["n_vehicle_types"] = data[[c for c in data.columns if c.startswith("veh_")]].sum(axis=1)
    data["intersection"] = data.intersection.fillna(0).astype(int)
    return data


def make_rare_event_pipeline(categorical, numeric, flags, resample: bool, C: float = 0.3):
    from imblearn.over_sampling import RandomOverSampler
    from imblearn.pipeline import Pipeline
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    prep = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical),
                              ("num", StandardScaler(), numeric), ("flag", "passthrough", flags)])
    steps = [("prep", prep)]
    if resample:  # inside the pipeline, so it only ever sees the training folds
        steps.append(("resample", RandomOverSampler(random_state=config.RANDOM_STATE)))
    steps.append(("clf", LogisticRegression(C=C, max_iter=3000, class_weight=None if resample else "balanced",
                                            random_state=config.RANDOM_STATE)))
    return Pipeline(steps)


def cost_threshold(y_true, probability, cost_miss=COST_MISS, cost_false_alarm=COST_FALSE_ALARM) -> tuple[float, pd.DataFrame]:
    grid = np.round(np.arange(0.05, 0.96, 0.01), 2)
    rows = []
    y_true = np.asarray(y_true)
    for t in grid:
        flagged = probability >= t
        misses = int(((~flagged) & (y_true == 1)).sum())
        false_alarms = int((flagged & (y_true == 0)).sum())
        rows.append({"threshold": t, "misses": misses, "false_alarms": false_alarms,
                     "cost": cost_miss * misses + cost_false_alarm * false_alarms})
    table = pd.DataFrame(rows)
    return float(table.loc[table.cost.idxmin(), "threshold"]), table


# Feature selection for the model: groups of columns, each refitted away on the training folds only.
FEATURE_GROUPS = {
    "province": ["province_group"], "road type": ["road_type"], "time of day": ["time_of_day"], "day type": ["day_type"],
    "season": ["season"], "number of vehicle types": ["n_vehicle_types"], "intersection": ["intersection"],
    "vehicle types": "veh_", "stated factors": "factor_", "collision type": "col_",
}
FEATURE_RULE = ("A feature group is dropped only if the model does better without it by more than one fold standard "
                "deviation of the full model (5-fold CV PR-AUC on the training years). A loss, or a change inside that "
                "noise, keeps the group.")


def _group_columns(group: str, columns) -> list[str]:
    spec = FEATURE_GROUPS[group]
    return [c for c in columns if c.startswith(spec)] if isinstance(spec, str) else [c for c in columns if c in spec]


def feature_group_check(train: pd.DataFrame, categorical, numeric, flags, resample: bool, C: float, cv) -> pd.DataFrame:
    """Refit the chosen pipeline without each feature group and record the CV PR-AUC (training years only).
    The table says which groups carry signal; groups_to_drop() applies the pre-set rule to it."""
    from sklearn.model_selection import cross_val_score

    def score(cat, num, fl):
        pipe = make_rare_event_pipeline(cat, num, fl, resample, C)
        folds = cross_val_score(pipe, train[cat + num + fl], train.multi_fatal, cv=cv, scoring="average_precision")
        return float(folds.mean()), float(folds.std())

    mean_all, sd_all = score(categorical, numeric, flags)
    rows = [{"without": "nothing (all features)", "n_features": len(categorical) + len(numeric) + len(flags),
             "cv_pr_auc": mean_all, "fold_sd": sd_all, "change": 0.0}]
    for group in FEATURE_GROUPS:
        remove = set(_group_columns(group, categorical + numeric + flags))
        if not remove:
            continue
        cat, num, fl = ([c for c in cols if c not in remove] for cols in (categorical, numeric, flags))
        mean, sd = score(cat, num, fl)
        rows.append({"without": group, "n_features": len(cat) + len(num) + len(fl), "cv_pr_auc": mean, "fold_sd": sd,
                     "change": mean - mean_all})
    return pd.DataFrame(rows)


def groups_to_drop(check: pd.DataFrame) -> list[str]:
    """Apply FEATURE_RULE to a feature_group_check() table."""
    full = check.iloc[0]
    return check[(check.without != full.without) & (check.change > full.fold_sd)].without.tolist()


def train_rare_event(crashes: pd.DataFrame) -> dict:
    """Train on 2018-2023 with 5-fold CV, run the feature-group check, choose the threshold from costs on
    out-of-fold predictions, then score 2024 once."""
    from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score
    from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_predict

    data = rare_event_frame(crashes)
    train = data[data.year < config.TEST_YEAR].copy()
    test = data[data.year == config.TEST_YEAR].copy()
    top = train.province.value_counts().head(5).index.tolist()  # learned from training rows only
    for frame in (train, test):
        frame["province_group"] = frame.province.where(frame.province.isin(top), "Other").fillna("Unknown")
    flags = [c for c in data.columns if c.startswith(("veh_", "factor_", "col_")) or c == "intersection"]
    flags = [c for c in flags if train[c].mean() >= 0.01]
    numeric = ["n_vehicle_types"]
    categorical = list(RARE_CATEGORICAL)
    features = categorical + numeric + flags
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=config.RANDOM_STATE)

    candidates = {}
    for label, resample in (("Class weights, no resampling", False), ("Random oversampling inside folds", True)):
        search = GridSearchCV(make_rare_event_pipeline(categorical, numeric, flags, resample),
                              {"clf__C": [0.03, 0.1, 0.3, 1.0]}, cv=cv, scoring="average_precision").fit(train[features], train.multi_fatal)
        candidates[label] = {"cv_pr_auc": float(search.best_score_), "C": float(search.best_params_["clf__C"]),
                             "resample": resample, "estimator": search.best_estimator_}
    chosen = max(candidates, key=lambda k: candidates[k]["cv_pr_auc"])
    model = candidates[chosen]["estimator"]

    # Feature selection: training years only, pre-set rule, the test year never seen.
    check = feature_group_check(train, categorical, numeric, flags, candidates[chosen]["resample"], candidates[chosen]["C"], cv)
    dropped_groups = groups_to_drop(check)
    if dropped_groups:
        remove = {c for g in dropped_groups for c in _group_columns(g, features)}
        categorical, numeric, flags = ([c for c in cols if c not in remove] for cols in (categorical, numeric, flags))
        features = categorical + numeric + flags
        model = make_rare_event_pipeline(categorical, numeric, flags, candidates[chosen]["resample"], candidates[chosen]["C"])
    oof = cross_val_predict(model, train[features], train.multi_fatal, cv=cv, method="predict_proba")[:, 1]
    threshold, cost_table = cost_threshold(train.multi_fatal, oof)
    sensitivity = {ratio: cost_threshold(train.multi_fatal, oof, ratio, 1.0)[0] for ratio in (2, 5, 10)}

    model.fit(train[features], train.multi_fatal)
    probability = model.predict_proba(test[features])[:, 1]
    flagged = probability >= threshold
    y = test.multi_fatal.to_numpy()
    encoder = model.named_steps["prep"].named_transformers_["cat"]
    widths = {col: len(cats) for col, cats in zip(categorical, encoder.categories_)}
    coefficients = pd.Series(model.named_steps["clf"].coef_[0], index=model.named_steps["prep"].get_feature_names_out())

    def group_recall(mask):
        positives = (y == 1) & mask
        return float((flagged & positives).sum() / positives.sum()) if positives.sum() else np.nan

    capital = (test.province == "Phnom Penh").to_numpy()
    results = {
        "trained_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "target": "Crash with two or more deaths (multi-fatality)", "train_years": "2018-2023", "test_year": config.TEST_YEAR,
        "train_rows": len(train), "test_rows": len(test), "base_rate_train": float(train.multi_fatal.mean()),
        "base_rate_test": float(y.mean()), "positives_test": int(y.sum()),
        "candidates": {k: {"cv_pr_auc": v["cv_pr_auc"], "C": v["C"]} for k, v in candidates.items()}, "chosen": chosen,
        "cost_miss": COST_MISS, "cost_false_alarm": COST_FALSE_ALARM, "threshold": threshold,
        "threshold_by_cost_ratio": {str(k): v for k, v in sensitivity.items()},
        "test_precision": float(precision_score(y, flagged, zero_division=0)), "test_recall": float(recall_score(y, flagged)),
        "test_flagged": int(flagged.sum()), "test_pr_auc": float(average_precision_score(y, probability)),
        "test_roc_auc": float(roc_auc_score(y, probability)),
        "accuracy_if_always_no": float(1 - y.mean()), "test_accuracy": float((flagged == y).mean()),
        "recall_phnom_penh": group_recall(capital), "recall_other_provinces": group_recall(~capital),
        "flag_rate_phnom_penh": float(flagged[capital].mean()) if capital.any() else np.nan,
        "flag_rate_other": float(flagged[~capital].mean()) if (~capital).any() else np.nan,
        "encoder_widths": widths, "n_features_after_encoding": int(sum(widths.values()) + len(numeric) + len(flags)),
        "features": features,
        "feature_rule": FEATURE_RULE, "feature_check": check.round(4).to_dict("records"),
        "feature_groups_dropped": dropped_groups,
        "coefficients": [{"feature": f, "coefficient": round(float(v), 4)} for f, v in coefficients.sort_values().items()],
    }
    cases = test.assign(probability=probability.round(3), flagged=flagged.astype(int))[
        ["event_id", "incident_date", "province", "road_type", "time_of_day", "vehicles_involved", "deaths",
         "multi_fatal", "probability", "flagged"]]
    return {"results": results, "cases": cases, "cost_table": cost_table, "model": model}


# --------------------------------------------------------------------------------------------
# Data quality
# --------------------------------------------------------------------------------------------

def imputation_before_after(crashes: pd.DataFrame) -> pd.DataFrame:
    """Deaths per fatal crash before and after the one fill (deaths = 1 where an article says someone died
    without a number), on the same scale, so the fill can be seen."""
    fatal = crashes[crashes.is_fatal == 1]
    assumed = fatal.casualty_note.fillna("").str.contains("assumed 1")
    bins = ["No number", "1", "2", "3", "4", "5 or more"]
    after = pd.Series(np.where(fatal.deaths >= 5, "5 or more", fatal.deaths.fillna(0).astype(int).astype(str)), index=fatal.index)
    before = after.where(~assumed, "No number")
    table = pd.DataFrame({"before": before.value_counts().reindex(bins, fill_value=0),
                          "after": after.value_counts().reindex(bins, fill_value=0)})
    table.index.name = "deaths per crash"
    table.attrs["filled"] = int(assumed.sum())
    return table


def missing_share(frame: pd.DataFrame, columns) -> pd.Series:
    return frame[columns].isna().mean().mul(100).round(1)


def missingness_by_year(crashes: pd.DataFrame, columns) -> pd.DataFrame:
    """Share of missing values per column and year: the missingness map for the news source."""
    blank = crashes[columns].isna() | crashes[columns].isin(["Unknown", "Not stated", "Unclassified"])
    return blank.groupby(crashes.year).mean().mul(100).round(0).T


def join_log_entry(step: str, left: int, right: int, after: int, unmatched: int, key: str, grain: str) -> dict:
    return {"step": step, "rows_left": left, "rows_right": right, "rows_after": after, "unmatched_left": unmatched,
            "key": key, "grain": grain}


# --------------------------------------------------------------------------------------------
# Build everything
# --------------------------------------------------------------------------------------------

def build_all(verbose: bool = True) -> dict:
    say = print if verbose else (lambda *a, **k: None)
    for folder in (config.PROCESSED, config.BOUNDARIES, config.REFERENCE, config.UPLOADS):
        folder.mkdir(parents=True, exist_ok=True)
    write_matching_table()

    if config.RAW_NEWS_XLSX.exists():
        public = build_public_crash_table()
        say(f"Public crash table rebuilt from the raw workbook: {len(public)} rows")
    else:
        public = load_public_crashes()
        say(f"Raw news workbook not present; kept {config.CRASHES_PUBLIC.name} ({len(public)} rows)")

    census, boundaries = build_census_and_boundaries()
    census.to_csv(config.CENSUS_CSV, index=False, encoding="utf-8")
    config.PROVINCE_GEOJSON.write_text(json.dumps(boundaries, ensure_ascii=False), encoding="utf-8")
    say(f"Census: {len(census)} provinces; boundaries: {config.PROVINCE_GEOJSON.stat().st_size / 1e3:.0f} KB")

    worldbank = build_worldbank()
    worldbank.to_csv(config.WORLDBANK_CSV, index=False)
    say(f"World Bank: {len(worldbank)} country-years, {worldbank.iso3.nunique()} countries")

    crashes = prepare_crashes(public)
    official = load_official()
    names = province_table()
    located = crashes.province.notna()
    panel = province_panel(crashes, census, worldbank, 2018, 2024)
    yearly = coverage_vs_official(crashes, official, worldbank)
    joins = [
        join_log_entry("News crashes x name-matching table", len(crashes), len(names), int(crashes.pro_code.notna().sum()),
                       int((located & crashes.pro_code.isna()).sum()), "province name -> pro_code", "crash"),
        join_log_entry("Unlocated crashes (no province in text)", len(crashes), 0, int(located.sum()),
                       int((~located).sum()), "-", "crash"),
        join_log_entry("Census layer x name-matching table", len(census), len(names), int(census.province.notna().sum()),
                       int(census.province.isna().sum()), "census name -> pro_code", "province"),
        join_log_entry("Province crash totals x census population", int(crashes.pro_code.nunique()), len(census), len(panel),
                       0, "pro_code", "province (2018-2024)"),
        join_log_entry("Census population x World Bank national population", len(census), int(worldbank[worldbank.iso3 == "KHM"].shape[0]),
                       len(province_population(census, worldbank, range(2018, 2025))), 0, "year (national growth factor)",
                       "province-year"),
        join_log_entry("Annual news totals x official totals x WHO modelled deaths", int(crashes.year.nunique()), len(official),
                       len(yearly), int(yearly.news_deaths.isna().sum()), "year", "year"),
    ]
    pd.DataFrame(joins).to_csv(config.JOIN_LOG, index=False)

    rare = train_rare_event(crashes)
    config.RARE_EVENT_JSON.write_text(json.dumps(rare["results"], indent=1, default=float), encoding="utf-8")
    rare["cases"].to_csv(config.RARE_EVENT_CASES, index=False)
    rare["cost_table"].to_csv(config.RARE_EVENT_COSTS, index=False)
    say(f"Rare event: base rate {rare['results']['base_rate_test']:.1%} in {config.TEST_YEAR}, "
        f"precision {rare['results']['test_precision']:.2f}, recall {rare['results']['test_recall']:.2f}")
    return {"public": public, "census": census, "worldbank": worldbank, "rare": rare["results"]}


if __name__ == "__main__":
    build_all(verbose="--quiet" not in sys.argv)
