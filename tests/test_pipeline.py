import numpy as np
import pandas as pd

from src import config
from src import pipeline as P


def test_class_breaks_and_assignment():
    values = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5, np.nan])
    edges = P.class_breaks(values, 4)
    classes = P.assign_classes(values, edges)
    assert edges[0] == 0.1 and edges[-1] == 0.5
    assert classes.iloc[0] == 0 and classes.iloc[4] == len(edges) - 2 and np.isnan(classes.iloc[5])
    assert len(P.class_labels(edges)) == len(edges) - 1


def test_monthly_series_fills_empty_months():
    crashes = pd.DataFrame({"period": pd.PeriodIndex(["2018-01", "2018-01", "2018-03"], freq="M"),
                            "deaths": [1, 0, 2], "is_fatal": [1, 0, 1], "severity_known": [1, 1, 1], "province": "Kep"})
    series = P.monthly_series(crashes, "reports", start="2018-01", end="2018-04")
    assert list(series) == [2, 0, 1, 0]
    assert list(P.monthly_series(crashes, "deaths", start="2018-01", end="2018-04")) == [1, 0, 2, 0]


def test_forecast_split_in_time_and_naive_baseline():
    index = pd.date_range("2018-01-01", "2024-12-01", freq="MS")
    series = pd.Series(10 + 5 * np.sin(2 * np.pi * index.month / 12), index=index)
    result = P.forecast_vs_naive(series)
    assert result["ok"] and result["test_months"] == 12 and result["train_end"] == "2023-12-01"
    assert np.allclose(result["test"].seasonal_naive.values, series["2023"].values)
    assert len(result["ahead"]) == 6


def test_robust_outliers_flag_spike_without_removing():
    series = pd.Series([5, 6, 5, 7, 6, 60, 5], dtype=float)
    out = P.robust_outliers(series)
    assert out.flagged.tolist() == [False] * 5 + [True, False] and len(out) == len(series)


def test_province_panel_rates_use_person_years():
    census = pd.DataFrame({"pro_code": [1, 2], "province": ["A", "B"], "population_2019": [100_000, 200_000],
                           "density_per_km2": [10, 20], "household_size": [4, 4]})
    worldbank = pd.DataFrame({"iso3": "KHM", "year": [2019, 2020], "population": [1000, 1100]})
    crashes = pd.DataFrame({"pro_code": [1, 1, 2], "year": [2019, 2020, 2020], "event_id": ["a", "b", "c"],
                            "deaths": [1, 0, 2], "is_fatal": [1, 0, 1], "severity_known": [1, 1, 1],
                            "road_type": "National road", "time_of_day": "Night (21-04)", "veh_motorcycle": 1})
    panel = P.province_panel(crashes, census, worldbank, 2019, 2020, min_reports=1).set_index("province")
    assert np.isclose(panel.loc["A", "person_years"], 100_000 + 110_000)
    assert np.isclose(panel.loc["A", "reports_per_100k_yr"], 2 / 210_000 * 1e5)
    assert panel.loc["A", "fatal_share_pct"] == 50


def test_official_totals_are_complete_and_sourced():
    official = P.load_official()
    assert official.year.is_unique and list(official.year) == list(range(int(official.year.min()), int(official.year.max()) + 1))
    assert official[["official_crashes", "official_deaths", "official_injured"]].notna().all().all()
    assert official.source_url.str.startswith("http").all() and official.source_date.notna().all()
    split = official.dropna(subset=["official_injured_serious", "official_injured_minor"])
    assert (split.official_injured_serious + split.official_injured_minor == split.official_injured).all()


def test_public_table_has_no_private_columns():
    public = pd.read_csv(config.CRASHES_PUBLIC, nrows=5)
    assert not set(P.PRIVATE_COLUMNS) & set(public.columns)


def test_cost_threshold_prefers_recall_when_misses_cost_more():
    y = np.array([1, 0, 0, 0, 1, 0])
    p = np.array([0.4, 0.3, 0.2, 0.1, 0.9, 0.35])
    cheap_misses, _ = P.cost_threshold(y, p, cost_miss=1, cost_false_alarm=5)
    dear_misses, _ = P.cost_threshold(y, p, cost_miss=10, cost_false_alarm=1)
    assert dear_misses <= cheap_misses


def test_correlation_rule_drops_the_later_of_a_redundant_pair():
    rng = np.random.default_rng(0)
    a = rng.normal(size=40)
    corr = pd.DataFrame({"x": a, "y": 2 * a + 0.01 * rng.normal(size=40), "z": rng.normal(size=40)}).corr(method="spearman")
    kept, dropped = P.select_indicators(corr, 0.8)
    assert kept == ["x", "z"]
    assert dropped == [{"dropped": "y", "kept": "x", "rho": dropped[0]["rho"]}] and dropped[0]["rho"] > 0.8


def test_province_pca_applies_the_rule_before_fitting():
    rng = np.random.default_rng(config.RANDOM_STATE)
    panel = pd.DataFrame({c: rng.normal(size=12) for c in P.PCA_INDICATORS})
    panel["deaths_per_100k_yr"] = 3 * panel.reports_per_100k_yr + 0.001 * rng.normal(size=12)
    panel["province"] = [f"P{i}" for i in range(12)]
    pca = P.province_pca(panel)
    assert pca["kept"] == [c for c in P.PCA_INDICATORS if c != "deaths_per_100k_yr"]
    assert pca["dropped"][0]["dropped"] == "deaths_per_100k_yr"
    assert list(pca["loadings"].index) == pca["kept"] and 0 < pca["variance_share"][0] <= 1
    assert len(pca["variance_share_all"]) == len(pca["variance_share"])


def test_groups_to_drop_applies_the_fold_noise_rule():
    check = pd.DataFrame([
        {"without": "nothing (all features)", "n_features": 10, "cv_pr_auc": 0.40, "fold_sd": 0.03, "change": 0.0},
        {"without": "a", "n_features": 9, "cv_pr_auc": 0.35, "fold_sd": 0.03, "change": -0.05},  # costs signal: keep
        {"without": "b", "n_features": 9, "cv_pr_auc": 0.41, "fold_sd": 0.03, "change": 0.01},   # inside noise: keep
        {"without": "c", "n_features": 9, "cv_pr_auc": 0.45, "fold_sd": 0.03, "change": 0.05},   # better without: drop
    ])
    assert P.groups_to_drop(check) == ["c"]


def test_feature_group_check_runs_on_training_rows_only():
    rng = np.random.default_rng(config.RANDOM_STATE)
    n = 120
    train = pd.DataFrame({
        "time_of_day": rng.choice(["Morning (05-11)", "Night (21-04)"], n), "day_type": rng.choice(["Weekday", "Weekend"], n),
        "season": rng.choice(["Dry (Nov-Apr)", "Rainy (May-Oct)"], n), "province_group": rng.choice(["Phnom Penh", "Other"], n),
        "road_type": rng.choice(["National road", "City street"], n), "n_vehicle_types": rng.integers(1, 4, n),
        "veh_heavy_truck": rng.integers(0, 2, n), "factor_speeding": rng.integers(0, 2, n), "col_rollover": rng.integers(0, 2, n),
        "intersection": rng.integers(0, 2, n)})
    train["multi_fatal"] = ((train.veh_heavy_truck + rng.random(n)) > 1.2).astype(int)
    from sklearn.model_selection import StratifiedKFold
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=config.RANDOM_STATE)
    check = P.feature_group_check(train, P.RARE_CATEGORICAL, ["n_vehicle_types"],
                                  ["veh_heavy_truck", "factor_speeding", "col_rollover", "intersection"], False, 0.3, cv)
    assert check.without.iloc[0] == "nothing (all features)" and check.n_features.iloc[0] == 10
    assert set(check.without) == {"nothing (all features)", *P.FEATURE_GROUPS}
    assert (check.n_features.iloc[1:] < 10).all() and check.change.iloc[0] == 0.0


def test_imputation_before_after_moves_filled_rows_from_blank_to_one():
    crashes = pd.DataFrame({"is_fatal": [1, 1, 1, 1, 0], "deaths": [1.0, 1.0, 2.0, 6.0, 0.0],
                            "casualty_note": ["death count assumed 1 (no number stated)", None, None, None, None]})
    table = P.imputation_before_after(crashes)
    assert table.loc["No number", "before"] == 1 and table.loc["No number", "after"] == 0
    assert table.loc["1", "before"] == 1 and table.loc["1", "after"] == 2
    assert table.loc["5 or more", "after"] == 1 and table.before.sum() == table.after.sum() == 4
    assert table.attrs["filled"] == 1
