"""Methods and ethics: where each course week appears, the number behind each decision, and what it cost."""
import numpy as np
import pandas as pd
import streamlit as st

from src import charts, config, ui
from src import pipeline as P

st.title("Methods and ethics")

crashes, census, worldbank, official = ui.crashes(False), ui.census(), ui.worldbank(), ui.official()
results, _, _ = ui.rare_event()
coverage = P.coverage_vs_official(crashes, official, worldbank).dropna(subset=["official_deaths"])
coverage_share = coverage.news_deaths.sum() / coverage.official_deaths.sum() if len(coverage) else float("nan")
coverage_years = f"{int(coverage.index.min())}-{int(coverage.index.max())}" if len(coverage) else "-"
panel = P.province_panel(crashes[crashes.year.between(2018, 2024)], census, worldbank, 2018, 2024)
pca = P.province_pca(panel)
series = P.monthly_series(crashes)
fc = P.forecast_vs_naive(series)
spikes = P.robust_outliers(series)
joins = pd.read_csv(config.JOIN_LOG)
public = P.load_public_crashes()
unlocated = crashes.province.isna().mean()
corr = pca["correlation"]
strongest = corr.where(~np.eye(len(corr), dtype=bool)).abs().stack().idxmax()
dropped_text = ("; ".join(f"{charts.indicator_label(d['dropped'])} dropped (rho {d['rho']:.2f} with {charts.indicator_label(d['kept'])})"
                          for d in pca["dropped"]) or f"no pair reaches |rho| {pca['limit']}, all {len(pca['kept'])} kept")
check = pd.DataFrame(results.get("feature_check", []))
dropped_groups = results.get("feature_groups_dropped", [])
n_groups = max(len(check) - 1, 0)
carries = int((check.change.iloc[1:] < -check.fold_sd.iloc[0]).sum()) if n_groups else 0

weeks = [
    ("1", "Preprocessing pipeline", "src/extract_accidents.py -> src/pipeline.py; data dictionary on the Data quality page",
     f"{len(public):,} raw rows -> {len(crashes):,} analysis-ready crashes", "Rows that are statistics, follow-ups, duplicates or "
     f"suspected rewrites are excluded ({len(public) - len(crashes)} rows)."),
    ("2", "Missing values", "Data quality page: missingness maps and reasons",
     f"Province missing for {unlocated:.1%} of crashes", "Unlocated crashes are dropped from the map; unknown times stay 'Unknown'."),
    ("3", "Outliers", "Robust z on monthly counts; 3 x IQR fences on deaths and injuries per crash",
     f"{int(spikes.flagged.sum())} of {len(series)} months flagged", "Flagged months stay in the series, so forecasts carry their noise."),
    ("4", "Normalisation", "Map: reports and deaths per 100,000 person-years, fatal shares; StandardScaler for the model and PCA",
     f"Phnom Penh is {panel.set_index('province').population_share_pct['Phnom Penh']:.0f}% of residents",
     "Population is from 2019 only; moving it to other years assumes national growth everywhere."),
    ("5", "Categorical encoding", "Province -> official code and ISO 3166-2 (KH-12); one-hot encoding in the model",
     f"{results['n_features_after_encoding']} model columns; widths {results['encoder_widths']}",
     "Province grouped to top 5 + Other so 25 provinces do not add 25 sparse columns; small provinces lose their identity."),
    ("6", "Feature engineering", "Rates, shares, year-on-year change, rolling 3-month share, day type, season, vehicle counts",
     "Each feature's claim is written in the data dictionary", "Every claim is an assumption that can be wrong, e.g. that the rainy season is May-October."),
    ("8", "Feature selection and PCA", f"Correlation rule (|rho| >= {pca['limit']} drops the later of a pair) then PCA on what is kept; "
     "feature-group check on the rare-event model (charts below)",
     f"{dropped_text}; PC1 keeps {pca['variance_share'][0]:.0%} of variance over {pca['provinces']} provinces "
     f"({pca['variance_share_all'][0]:.0%} before the rule); {carries} of {n_groups} model feature groups carry signal, "
     f"{len(dropped_groups)} dropped",
     "Only provinces with 10+ reports enter the PCA; the group check has few positives, so a change inside one fold sd cannot "
     "be told from noise."),
    ("9", "Data integration", "News x name table x census x World Bank x official totals",
     f"{len(joins)} joins logged; {int(joins.unmatched_left.sum())} unmatched rows (all unlocated crashes)",
     "Three ODC spellings differ from the news spelling (Otdar Meanchey, Mondul Kiri, Ratanak Kiri); matched by code."),
    ("10", "Imbalanced data", "Multi-fatality crashes; class weights vs oversampling inside folds; cost threshold",
     f"Base rate {results['base_rate_test']:.1%}; precision {results['test_precision']:.2f}, recall {results['test_recall']:.2f}",
     f"A 5:1 miss cost gives threshold {results['threshold']:.2f}; {results['test_flagged']} of {results['test_rows']} crashes flagged to catch "
     f"{round(results['test_recall'] * results['positives_test'])} of {results['positives_test']}."),
    ("11", "Time series", "Monthly frequency, STL trend and season, split at 2024, Holt-Winters vs seasonal naive",
     f"MAE {fc['mae_model']:.1f} vs {fc['mae_naive']:.1f}" if fc.get("ok") else "not enough data",
     "The 'season' mostly reflects collection batches, so the forecast cannot be used to plan."),
    ("12", "Visualisation", "Every chart title states its finding; counts start at zero; maps state quantile class breaks",
     "One-hue blue ramp; grey for too few reports", "Quantile classes make neighbours look different even when values are close."),
    ("13", "One pipeline", "ColumnTransformer + (oversampler) + LogisticRegression in one pipeline; 5-fold CV on 2018-2023; 2024 used once",
     f"CV PR-AUC {results['candidates'][results['chosen']]['cv_pr_auc']:.2f}; test PR-AUC {results['test_pr_auc']:.2f}",
     "The test year is small (" + str(results['positives_test']) + " positives), so its scores are uncertain."),
    ("14", "Ethics", "See below", f"Recall {results['recall_other_provinces']:.0%} outside vs {results['recall_phnom_penh']:.0%} in Phnom Penh",
     "Article text and sub-province places are withheld, which removes district and commune maps."),
    ("7, 15", "Defending the work", "Restart and Run All on notebooks/analysis.ipynb; random_state = 42 everywhere; tests in tests/",
     "pytest suite for validate.py, fetch.py and pipeline.py (python -m pytest -q)", "-"),
]
st.dataframe(pd.DataFrame(weeks, columns=["week", "skill", "where in the project", "number behind the decision", "what it cost"]),
             hide_index=True, width="stretch", row_height=70)

# ---------------- Feature selection ----------------
st.subheader("Feature selection: the rule, the number, and what was dropped")
st.markdown(
    f"**Week 8, province indicators.** Rule set before looking at the data: of any two indicators with |Spearman rho| >= "
    f"{pca['limit']}, the one listed later is dropped (the list is ordered by completeness: reports count every located crash, "
    f"deaths need a stated number). Result: {dropped_text}. PCA then runs on the {len(pca['kept'])} kept indicators over "
    f"{pca['provinces']} provinces with 10+ reports.")
pair = strongest
heat_title = (f"One pair above |rho| = {pca['limit']}: {charts.indicator_label(pair[0])} and {charts.indicator_label(pair[1])} "
              f"(rho {corr.loc[pair]:.2f})" if pca["dropped"] else
              f"No pair reaches |rho| = {pca['limit']}: strongest is {charts.indicator_label(pair[0])} and "
              f"{charts.indicator_label(pair[1])} ({corr.loc[pair]:.2f})")
loads = pca["loadings"]["PC1"]
top_loads = loads.reindex(loads.abs().sort_values(ascending=False).index[:3])
a, b = st.columns([3, 2], gap="medium")
a.plotly_chart(charts.correlation_heatmap(corr, heat_title, [d["dropped"] for d in pca["dropped"]]), config={"displayModeBar": False})
b.plotly_chart(charts.variance_chart(pca["variance_share"], pca["variance_share_all"], len(pca["kept"]), len(P.PCA_INDICATORS),
                                     f"PC1 keeps {pca['variance_share'][0]:.0%} of the variance after the rule "
                                     f"({pca['variance_share_all'][0]:.0%} before)"), config={"displayModeBar": False})
b.caption("PC1 loads most on " + ", ".join(f"{charts.indicator_label(k)} ({v:+.2f})" for k, v in top_loads.items())
          + ". It reads as an index of where crashes get reported, not of danger, so it is reported here and not used as a model feature.")
b.dataframe(pca["loadings"].round(2).rename(index=charts.indicator_label), width="stretch")

if n_groups:
    st.markdown(
        f"**Weeks 10 and 13, rare-event model.** {results['feature_rule']} Result: {carries} of {n_groups} groups carry signal "
        f"(dropping one costs more than fold noise); {', '.join(dropped_groups) if dropped_groups else 'none'} dropped. "
        f"The model keeps {len(results['features'])} features, {results['n_features_after_encoding']} columns after encoding, "
        f"and the test year was never used for this choice.")
    coefs = pd.Series({r["feature"]: r["coefficient"] for r in results["coefficients"]})
    a, b = st.columns(2, gap="medium")
    a.plotly_chart(charts.ablation_chart(
        check, f"{carries} of {n_groups} feature groups carry signal; {len(dropped_groups)} dropped under the rule"),
        config={"displayModeBar": False})
    b.plotly_chart(charts.coefficient_chart(
        coefs, f"'{charts.feature_label(coefs.idxmax())}' raises and '{charts.feature_label(coefs.idxmin())}' lowers the odds most"
               "<br><sup>Largest coefficients of the final model; associations in reported crashes, not causes</sup>"),
        config={"displayModeBar": False})
else:
    st.info("Run `python -m src.pipeline` to add the feature-group check to the rare-event results.")

st.subheader("Ethics")
st.markdown(f"""
**Who is missing.** The sample holds the crashes that Khmer news chose to cover: about {coverage_share:.0%} of the deaths the
National Road Safety Committee counted in {coverage_years}, and the WHO model puts the true toll at about twice the official count.
Provinces with few journalists, crashes with no injury, and victims who died later in hospital are all under-counted.
Foreign-language outlets and social media are not in the sample.

**Risk of identifying people.** Articles name victims, give ages and home villages, and publish plate numbers. The portal
publishes no article text, headline, district, commune, village, kilometre marker or exact time; the smallest place shown is
the province, and the smallest time unit on a chart is the month. The upload format has no column for names, ages or plates;
the only free text is a short road name and source note, and uploaders are asked to keep people out of them.

**Copyright.** {int(public.source_hint.eq('khmernews.news').sum())} rows carry a khmernews.news no-copying notice and
{int(public.source_hint.eq('VOD (CCIM)').sum())} a VOD/CCIM copyright footer, so the raw workbook stays out of the repository.

**Rules that treat groups differently.** The rare-event rule flags {results['flag_rate_phnom_penh']:.0%} of Phnom Penh crashes and
{results['flag_rate_other']:.0%} of crashes elsewhere, and its recall is {results['recall_phnom_penh']:.0%} in the capital. A team using it
to decide which crashes to verify first would systematically skip the capital.

**Suspected AI rewrites.** Some rows read like rewritten articles that dramatise severity. They are flagged and excluded; their
origin is not known.

**Modelled statistics.** WHO road mortality figures are estimates. Comparing ASEAN members whose death registration differs in
quality is a comparison of models as much as of roads.
""")
