"""The findings page: each finding is one sentence with a number, computed from the data, plus the chart that proves it.
The notebook calls the same function, so every number on the page can be reproduced."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import charts, config
from src import pipeline as P


@dataclass
class Finding:
    key: str
    sentence: str
    number: str
    caveat: str
    figure: object
    hypothesis: str = ""


def _p(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def compute_findings(crashes: pd.DataFrame, census: pd.DataFrame, worldbank: pd.DataFrame, official: pd.DataFrame,
                     start_year: int = 2018, end_year: int = 2024) -> list[Finding]:
    window = crashes[crashes.year.between(start_year, end_year)]
    panel = P.province_panel(window, census, worldbank, start_year, end_year)
    findings = []

    # 1. Fatal share inside vs outside the capital (H1a)
    t = P.test_capital_vs_rest(window)
    supported = t["fatal_share_outside"] > t["fatal_share_inside"] and t["p_value_one_sided"] < 0.05
    road = window[window.severity_known == 1].groupby("road_type").is_fatal.agg(["mean", "size"])
    road = road[road["size"] >= 10].sort_values("mean")
    findings.append(Finding(
        "capital_fatal_share",
        f"Outside Phnom Penh {t['fatal_share_outside']:.0%} of reported crashes were fatal, against "
        f"{t['fatal_share_inside']:.0%} inside the capital ({t['ratio']:.1f} times as often; z = {t['z']:.1f}, {_p(t['p_value_one_sided'])}).",
        f"{t['ratio']:.1f}x", "The news chooses which crashes to report: a non-fatal crash in a province may simply not make the news.",
        charts.bar_compare(["Phnom Penh", "Other provinces"], [100 * t["fatal_share_inside"], 100 * t["fatal_share_outside"]],
                           f"Reported crashes outside the capital are {t['ratio']:.1f}x as often fatal", suffix="%",
                           colours=[charts.NO_DATA, charts.BLUE]),
        "H1a " + ("not rejected" if supported else "rejected")))

    # 2. Coverage bias: report share vs population share (H1b)
    c = P.test_coverage_vs_population(panel)
    findings.append(Finding(
        "capital_coverage",
        f"Phnom Penh holds {c['capital_report_share']:.0f}% of reported crashes but {c['capital_population_share']:.0f}% of the "
        f"population, so it is reported {c['rate_ratio']:.1f} times as often per resident as the rest of the country "
        f"(chi-square against population shares, {_p(c['p_value'])}).",
        f"{c['rate_ratio']:.1f}x", "This measures where journalists are, not where crashes happen; per-person crash risk cannot be read from it.",
        charts.grouped_share_chart(panel, f"The capital's share of reports is {c['capital_report_share'] / c['capital_population_share']:.1f}x its share of residents"),
        "H1b " + ("not rejected" if c["p_value"] < 0.05 and c["rate_ratio"] > 1 else "rejected")))

    # 3. Coverage of official deaths
    cov = P.coverage_vs_official(crashes, official, worldbank).dropna(subset=["official_deaths"])
    if len(cov):
        share = cov.news_deaths.sum() / cov.official_deaths.sum()
        crash_share = cov.news_reports.sum() / cov.official_crashes.sum() if cov.official_crashes.sum() else np.nan
        years = f"{int(cov.index.min())}-{int(cov.index.max())}"
        fig = charts.bar_compare([str(y) for y in cov.index], list(cov.news_deaths),
                                 f"The news sample records {share:.0%} of officially counted road deaths ({years})")
        fig.data[0].name = "Deaths in news sample"
        fig.add_bar(x=[str(y) for y in cov.index], y=cov.official_deaths, name="Official deaths (unverified figures)",
                    marker_color=charts.NO_DATA, marker_line_width=0, text=[f"{v:,.0f}" for v in cov.official_deaths],
                    textposition="outside")
        fig.update_layout(barmode="group", showlegend=True)
        findings.append(Finding(
            "official_coverage",
            f"In {years} the news sample recorded {cov.news_deaths.sum():,.0f} road deaths against {cov.official_deaths.sum():,.0f} "
            f"in the National Road Safety Committee's totals, about {share:.0%}"
            + (f", and {cov.news_reports.sum():,.0f} of {cov.official_crashes.sum():,.0f} recorded crashes ({crash_share:.0%})."
               if pd.notna(crash_share) else "."),
            f"{share:.0%}", "The official totals are the committee's annual counts as released on ministry and state-media pages "
            "(one source per year in official_totals.csv); the committee's own report is not online. WHO's model puts 2021 deaths "
            "near 3,000, about twice the national count, so even the official series is a lower bound.", fig))

    # 4. ASEAN trend (H2)
    a = P.test_asean_trend(worldbank)
    first = int(worldbank.dropna(subset=["road_deaths_per_100k"]).year.min())
    table = P.asean_table(worldbank, a["year"], first)
    rose = a["khm_change"] > 0 and a["others_fell"] > a["others"] / 2
    ordered = table.sort_values("change_since_base")
    findings.append(Finding(
        "asean_trend",
        f"Cambodia's WHO-modelled road death rate {'rose' if a['khm_change'] > 0 else 'fell'} by {abs(a['khm_change']):.1f} to "
        f"{a['khm_rate']:.1f} per 100,000 between {first} and {a['year']}, while {a['others_fell']} of the other "
        f"{a['others']} ASEAN members' rates fell; Cambodia ranks {a['khm_rank']} of {a['members']}.",
        f"{a['khm_change']:+.1f}", "These are modelled estimates, not counts; their quality differs between countries.",
        charts.bar_compare(list(ordered.country), list(ordered.change_since_base),
                           f"Change in road deaths per 100,000, {first} to {a['year']}: {int((table.change_since_base > 0).sum())} of "
                           f"{a['members']} members rose",
                           colours=[charts.ORANGE if i == "KHM" else charts.NO_DATA for i in ordered.index],
                           text_format="{:+.1f}", horizontal=True, height=420),
        "H2 " + ("not rejected" if rose else "rejected")))

    # 5. Time series: forecast against naive, and outlier months
    series = P.monthly_series(crashes)
    fc = P.forecast_vs_naive(series)
    out = P.robust_outliers(series)
    if fc.get("ok"):
        gain = 1 - fc["mae_model"] / fc["mae_naive"]
        verdict = "beats" if fc["beats_naive"] else "does not beat"
        findings.append(Finding(
            "forecast",
            f"On the held-out {config.TEST_YEAR} months the Holt-Winters forecast {verdict} 'same month last year' "
            f"(mean absolute error {fc['mae_model']:.1f} against {fc['mae_naive']:.1f} reports, {gain:+.0%}), but "
            f"{int(out.flagged.sum())} of {len(series)} months are flagged collection spikes.",
            f"{fc['mae_model']:.1f} vs {fc['mae_naive']:.1f}",
            "The monthly series mostly records when articles were collected; neither forecast says how many crashes will happen.",
            charts.time_chart(series, P.decompose(series), fc, out,
                              f"Reported crashes per month: forecast {verdict} the seasonal naive baseline by {abs(gain):.0%}")))
    return findings
