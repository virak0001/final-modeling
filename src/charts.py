"""Plotly figures shared by the portal and the notebook. Titles state the finding; axes start at zero for counts."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.pipeline import MAP_MEASURES, assign_classes, class_breaks, class_labels

# Reference palette (validated): categorical slots, one-hue blue ramp for magnitude, reserved status colours.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, SECONDARY, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
SERIOUS = "#ec835a"  # status: flagged outlier (always shown with a label)
NO_DATA = "#d9d8d2"
SEQUENTIAL = ["#cde2fb", "#86b6ef", "#5598e7", "#2a78d6", "#184f95", "#0d366b"]
FONT = dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=13)


def _layout(fig: go.Figure, title: str, height: int = 420, **kwargs) -> go.Figure:
    fig.update_layout(title=dict(text=title, x=0, xanchor="left", font=dict(size=15)), height=height, font=FONT,
                      margin=dict(l=10, r=10, t=56, b=10), hoverlabel=dict(font_size=12),
                      legend=dict(orientation="h", yanchor="top", y=-0.12, x=0, title=None), **kwargs)
    return fig


def _ramp(k: int) -> list[str]:
    picks = np.linspace(0, len(SEQUENTIAL) - 1, k).round().astype(int)
    return [SEQUENTIAL[i] for i in picks]


def province_map(panel: pd.DataFrame, measure: str, geojson: dict, selected: str | None = None,
                 title: str | None = None, k: int = 5, height: int = 520) -> tuple[go.Figure, list[float]]:
    """Choropleth with stated quantile class breaks. Provinces with too few reports for a share are grey."""
    values = panel[measure]
    edges = class_breaks(values, k)
    classes = assign_classes(values, edges)
    labels = class_labels(edges)
    colours = _ramp(len(labels))
    fig = go.Figure()
    for i, (label, colour) in enumerate(zip(labels, colours)):
        part = panel[classes == i]
        if part.empty:
            continue
        fig.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.pro_code", locations=part.pro_code, z=np.zeros(len(part)),
            colorscale=[[0, colour], [1, colour]], showscale=False, name=label, showlegend=True,
            marker=dict(line=dict(color="#ffffff", width=0.8)), customdata=part[["province", measure, "reports"]].values,
            hovertemplate="<b>%{customdata[0]}</b><br>" + MAP_MEASURES[measure] + ": %{customdata[1]:.2f}"
                          "<br>Reports in period: %{customdata[2]}<extra></extra>"))
    missing = panel[classes.isna()]
    if len(missing):
        fig.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.pro_code", locations=missing.pro_code, z=np.zeros(len(missing)),
            colorscale=[[0, NO_DATA], [1, NO_DATA]], showscale=False, name="Too few reports (<10)", showlegend=True,
            marker=dict(line=dict(color="#ffffff", width=0.8)), customdata=missing[["province", "reports"]].values,
            hovertemplate="<b>%{customdata[0]}</b><br>Only %{customdata[1]} reports: share not shown<extra></extra>"))
    if selected and selected in set(panel.province):
        row = panel[panel.province == selected]
        fig.add_trace(go.Choropleth(geojson=geojson, featureidkey="properties.pro_code", locations=row.pro_code, z=[0],
                                    colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
                                    marker=dict(line=dict(color=INK, width=3)), name=f"Selected: {selected}",
                                    hoverinfo="skip", showlegend=True))
    fig.update_geos(fitbounds="locations", visible=False)
    _layout(fig, title or MAP_MEASURES[measure], height=height)
    fig.update_layout(legend=dict(orientation="h", y=0, yanchor="top", x=0, title_text="Quantile classes: "),
                      clickmode="event+select", dragmode=False, margin=dict(l=0, r=0, t=56, b=40))
    return fig, edges


def time_chart(series: pd.Series, decomposition: pd.DataFrame | None = None, forecast: dict | None = None,
               outliers: pd.DataFrame | None = None, title: str = "", height: int = 440,
               highlight: tuple | None = None) -> go.Figure:
    fig = go.Figure()
    if highlight:
        fig.add_vrect(x0=highlight[0], x1=highlight[1], fillcolor=BLUE, opacity=0.06, line_width=0,
                      annotation_text="Selected period", annotation_position="top left", annotation_font_color=SECONDARY)
    fig.add_trace(go.Scatter(x=series.index, y=series.values, name="Recorded", mode="lines",
                             line=dict(color=BLUE, width=2), hovertemplate="%{y:.1f}<extra>Recorded</extra>"))
    if decomposition is not None:
        fig.add_trace(go.Scatter(x=decomposition.index, y=decomposition.trend, name="Trend (STL)", mode="lines",
                                 line=dict(color=SECONDARY, width=2, dash="dash"), hovertemplate="%{y:.1f}<extra>Trend</extra>"))
    if forecast and forecast.get("ok"):
        for part, label in ((forecast["test"], "held-out 2024"), (forecast["ahead"], "ahead")):
            fig.add_trace(go.Scatter(x=list(part.index) + list(part.index[::-1]), y=list(part.high80) + list(part.low80[::-1]),
                                     fill="toself", fillcolor="rgba(235,104,52,0.15)", line=dict(width=0), hoverinfo="skip", mode="lines",
                                     name="80% band", showlegend=label == "ahead"))
            fig.add_trace(go.Scatter(x=part.index, y=part.model, name="Forecast (Holt-Winters)", mode="lines",
                                     line=dict(color=ORANGE, width=2), showlegend=label == "ahead",
                                     hovertemplate="%{y:.1f}<extra>Forecast " + label + "</extra>"))
            fig.add_trace(go.Scatter(x=part.index, y=part.seasonal_naive, name="Naive: same month last year", mode="lines",
                                     line=dict(color=MUTED, width=2, dash="dot"), showlegend=label == "ahead",
                                     hovertemplate="%{y:.1f}<extra>Seasonal naive</extra>"))
    if outliers is not None and outliers.flagged.any():
        flagged = outliers[outliers.flagged]
        fig.add_trace(go.Scatter(x=flagged.index, y=flagged.value, mode="markers", name="Flagged outlier (|robust z| > 3.5)",
                                 marker=dict(color=SERIOUS, size=10, symbol="diamond", line=dict(color="#ffffff", width=2)),
                                 hovertemplate="%{x|%b %Y}: %{y:.0f} (flagged)<extra></extra>"))
    _layout(fig, title, height=height, hovermode="x unified")
    fig.update_yaxes(rangemode="tozero", gridcolor=GRID, zeroline=True, zerolinecolor="#c3c2b7")
    if forecast and forecast.get("ok"):
        top = float(np.nanmax(series.values)) * 1.25
        band_top = float(max(forecast["test"].high80.max(), forecast["ahead"].high80.max()))
        if band_top > top:  # keep the recorded series readable; say that the band continues
            fig.update_yaxes(range=[0, top])
            fig.add_annotation(x=forecast["ahead"].index[-1], y=top, text=f"band reaches {band_top:.0f}", showarrow=False,
                               xanchor="right", yanchor="top", font=dict(color=SECONDARY, size=11))
    fig.update_xaxes(showgrid=False)
    return fig


def yoy_chart(yoy: pd.Series, title: str) -> go.Figure:
    colours = np.where(yoy >= 0, BLUE, ORANGE)
    fig = go.Figure(go.Bar(x=yoy.index, y=yoy.values, marker_color=colours, marker_line_width=0,
                           hovertemplate="%{x|%b %Y}: %{y:+.0f}%<extra></extra>", name="Change on a year earlier"))
    _layout(fig, title, height=300)
    fig.update_yaxes(ticksuffix="%", gridcolor=GRID, zerolinecolor="#c3c2b7")
    return fig


def seasonal_chart(decomposition: pd.DataFrame, title: str) -> go.Figure:
    factor = decomposition.seasonal_factor.groupby(decomposition.index.month).mean()
    months = pd.to_datetime(factor.index, format="%m").strftime("%b")
    fig = go.Figure(go.Bar(x=months, y=factor.values, marker_color=BLUE, marker_line_width=0,
                           hovertemplate="%{x}: x%{y:.2f}<extra></extra>"))
    fig.add_hline(y=1, line_color=MUTED, line_dash="dot", annotation_text="No seasonal effect", annotation_position="top left")
    _layout(fig, title, height=300)
    fig.update_yaxes(rangemode="tozero", gridcolor=GRID, title="Seasonal factor (x average)")
    return fig


def asean_map(table: pd.DataFrame, measure: str, label: str, selected: str | None = None) -> go.Figure:
    data = table.reset_index()
    edges = class_breaks(data[measure], 4)
    classes = assign_classes(data[measure], edges)
    labels = class_labels(edges)
    diverging = measure.startswith("change")
    colours = (["#2a78d6", "#86b6ef", "#f4b8a8", "#e34948"] if diverging else _ramp(len(labels)))[:len(labels)]
    fig = go.Figure()
    for i, (lab, colour) in enumerate(zip(labels, colours)):
        part = data[classes == i]
        if part.empty:
            continue
        fig.add_trace(go.Choropleth(locations=part.iso3, z=np.zeros(len(part)), colorscale=[[0, colour], [1, colour]],
                                    showscale=False, name=lab, marker_line_color="#ffffff", marker_line_width=0.6,
                                    customdata=part[["country", measure, "rank"]].values,
                                    hovertemplate="<b>%{customdata[0]}</b><br>" + label + ": %{customdata[1]:.1f}"
                                                  "<br>Rank on deaths per 100k: %{customdata[2]} of " + str(len(data)) + "<extra></extra>"))
    outline = data[data.iso3 == (selected or "KHM")]
    fig.add_trace(go.Choropleth(locations=outline.iso3, z=[0], colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
                                showscale=False, marker_line_color=INK, marker_line_width=2.5,
                                name=f"Outlined: {outline.country.iloc[0] if len(outline) else ''}", hoverinfo="skip"))
    fig.update_geos(fitbounds="locations", showcountries=True, countrycolor="#ffffff", showland=True, landcolor="#f0efec",
                    showocean=False, showframe=False, projection_type="mercator")
    _layout(fig, f"{label}, {table.attrs.get('year', '')}", height=460)
    fig.update_layout(legend=dict(orientation="h", y=0, yanchor="top", x=0, title_text="Quantile classes: "),
                      clickmode="event+select", dragmode=False, margin=dict(l=0, r=0, t=56, b=40))
    return fig


def asean_paths(worldbank: pd.DataFrame, highlight: str = "KHM", title: str = "") -> go.Figure:
    rates = worldbank.dropna(subset=["road_deaths_per_100k"])
    fig = go.Figure()
    for iso, part in rates.groupby("iso3"):
        if iso == highlight:
            continue
        fig.add_trace(go.Scatter(x=part.year, y=part.road_deaths_per_100k, mode="lines", line=dict(color=NO_DATA, width=1.5),
                                 name=part.country.iloc[0], showlegend=False,
                                 hovertemplate=part.country.iloc[0] + " %{x}: %{y:.1f}<extra></extra>"))
    median = rates.groupby("year").road_deaths_per_100k.median()
    fig.add_trace(go.Scatter(x=median.index, y=median.values, mode="lines", line=dict(color=SECONDARY, width=2, dash="dash"),
                             name="ASEAN median", hovertemplate="Median %{x}: %{y:.1f}<extra></extra>"))
    own = rates[rates.iso3 == highlight]
    fig.add_trace(go.Scatter(x=own.year, y=own.road_deaths_per_100k, mode="lines+markers", line=dict(color=BLUE, width=2.5),
                             marker=dict(size=8, line=dict(color="#ffffff", width=1.5)), name=own.country.iloc[0],
                             hovertemplate=own.country.iloc[0] + " %{x}: %{y:.1f}<extra></extra>"))
    _layout(fig, title, height=420, hovermode="closest")
    fig.update_yaxes(rangemode="tozero", gridcolor=GRID, title="Road deaths per 100,000 (WHO modelled)")
    return fig


def bar_compare(labels, values, title: str, suffix: str = "", colours=None, text_format: str = "{:.0f}",
                height: int = 320, horizontal: bool = False) -> go.Figure:
    colours = colours or [BLUE] * len(values)
    text = [text_format.format(v) + suffix for v in values]
    bar = go.Bar(x=values if horizontal else labels, y=labels if horizontal else values, orientation="h" if horizontal else "v",
                 marker_color=colours, marker_line_width=0, text=text, textposition="outside", cliponaxis=False,
                 hovertemplate="%{" + ("y" if horizontal else "x") + "}: %{text}<extra></extra>")
    fig = go.Figure(bar)
    _layout(fig, title, height=height)
    axis = fig.update_xaxes if horizontal else fig.update_yaxes
    axis(rangemode="tozero", gridcolor=GRID, ticksuffix=suffix, showticklabels=True)
    return fig


def grouped_share_chart(frame: pd.DataFrame, title: str) -> go.Figure:
    """Report share against population share for each province: equal bars would mean proportional coverage."""
    data = frame.sort_values("population_share_pct")
    fig = go.Figure()
    fig.add_trace(go.Bar(y=data.province, x=data.population_share_pct, orientation="h", name="Share of population (census 2019)",
                         marker_color=NO_DATA, marker_line_width=0, hovertemplate="%{y}: %{x:.1f}%<extra>Population</extra>"))
    fig.add_trace(go.Bar(y=data.province, x=data.report_share_pct, orientation="h", name="Share of reported crashes",
                         marker_color=BLUE, marker_line_width=0, hovertemplate="%{y}: %{x:.1f}%<extra>Reports</extra>"))
    _layout(fig, title, height=640, barmode="group", bargap=0.25, bargroupgap=0.1)
    fig.update_xaxes(ticksuffix="%", gridcolor=GRID, rangemode="tozero")
    return fig


def missingness_heatmap(table: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure(go.Heatmap(z=table.values, x=[str(int(c)) for c in table.columns], y=table.index,
                               colorscale=[[0, "#ffffff"], [1, SEQUENTIAL[-2]]], zmin=0, zmax=100,
                               colorbar=dict(title="% missing", ticksuffix="%"), xgap=2, ygap=2,
                               hovertemplate="%{y}, %{x}: %{z:.0f}% missing<extra></extra>"))
    _layout(fig, title, height=max(320, 26 * len(table) + 120))
    return fig


def cost_curve(table: pd.DataFrame, chosen: float, title: str) -> go.Figure:
    fig = go.Figure(go.Scatter(x=table.threshold, y=table.cost, mode="lines", line=dict(color=BLUE, width=2),
                               hovertemplate="Threshold %{x:.2f}: cost %{y:.0f}<extra></extra>", name="Expected cost"))
    fig.add_vline(x=chosen, line_color=ORANGE, line_width=2, annotation_text=f"Chosen {chosen:.2f}",
                  annotation_position="top right")
    _layout(fig, title, height=300)
    fig.update_xaxes(title="Probability threshold", gridcolor=GRID)
    fig.update_yaxes(title="Cost on training folds", rangemode="tozero", gridcolor=GRID)
    return fig


# ---------------- Feature selection and the one fill ----------------

DIVERGING = [[0, "#e34948"], [0.5, "#f0efec"], [1, BLUE]]  # red <-> blue with a neutral grey midpoint (reference pair)
INDICATOR_LABELS = {
    "reports_per_100k_yr": "Reports per 100k person-years", "deaths_per_100k_yr": "Deaths per 100k person-years",
    "fatal_share_pct": "Fatal share %", "density_per_km2": "Density per km2", "household_size": "Household size",
    "national_road_share_pct": "National road share %", "night_share_pct": "Night share %",
    "motorcycle_share_pct": "Motorcycle share %",
}
FEATURE_PREFIXES = {"cat__province_group_": "Province: ", "cat__time_of_day_": "Time of day: ", "cat__day_type_": "Day: ",
                    "cat__season_": "Season: ", "cat__road_type_": "Road: ", "flag__veh_": "Vehicle: ",
                    "flag__factor_": "Factor: ", "flag__col_": "Collision: ", "flag__intersection": "At an intersection",
                    "num__n_vehicle_types": "Number of vehicle types"}


def indicator_label(column: str) -> str:
    return INDICATOR_LABELS.get(column, column.replace("_", " "))


def feature_label(name: str) -> str:
    for prefix, label in FEATURE_PREFIXES.items():
        if name.startswith(prefix):
            rest = name[len(prefix):].replace("_", " ")
            return label + rest if rest else label
    return name.replace("_", " ")


def correlation_heatmap(corr: pd.DataFrame, title: str, dropped=(), height: int = 480) -> go.Figure:
    """Spearman correlations on a diverging scale (red negative, blue positive, grey zero); the diagonal is blank,
    and an indicator the rule dropped is marked in its label."""
    labels = [indicator_label(c) + (" (dropped)" if c in dropped else "") for c in corr.columns]
    z = corr.values.astype(float).copy()
    np.fill_diagonal(z, np.nan)
    text = np.where(np.isnan(z), "", np.round(z, 2).astype(str))
    fig = go.Figure(go.Heatmap(z=z, x=labels, y=labels, zmin=-1, zmax=1, colorscale=DIVERGING, text=text,
                               texttemplate="%{text}", textfont=dict(size=11, color=INK), xgap=2, ygap=2,
                               colorbar=dict(title="Spearman rho", tickvals=[-1, -0.5, 0, 0.5, 1], thickness=12),
                               hovertemplate="%{y} vs %{x}: rho = %{z:.2f}<extra></extra>", hoverongaps=False))
    _layout(fig, title, height=height)
    fig.update_xaxes(tickangle=-35, showgrid=False, tickfont=dict(size=11))
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(size=11))
    fig.update_layout(margin=dict(l=10, r=10, t=56, b=10))
    return fig


def variance_chart(share, share_all, n_after: int, n_before: int, title: str) -> go.Figure:
    """Share of variance each component keeps after the correlation rule, with the share before it in grey."""
    labels = [f"PC{i + 1}" for i in range(len(share))]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=100 * np.asarray(share_all[:len(share)]), name=f"Before the rule ({n_before} indicators)",
                         marker_color=NO_DATA, marker_line_width=0, hovertemplate="%{x}: %{y:.1f}%<extra>Before</extra>"))
    fig.add_trace(go.Bar(x=labels, y=100 * np.asarray(share), name=f"After the rule ({n_after} indicators)", marker_color=BLUE,
                         marker_line_width=0, text=[f"{100 * v:.0f}%" for v in share], textposition="outside", cliponaxis=False,
                         hovertemplate="%{x}: %{y:.1f}%<extra>After</extra>"))
    _layout(fig, title, height=320, barmode="group", bargap=0.3, bargroupgap=0.08)
    fig.update_yaxes(rangemode="tozero", ticksuffix="%", gridcolor=GRID, title="Variance kept")
    fig.update_xaxes(showgrid=False)
    return fig


def ablation_chart(check: pd.DataFrame, title: str) -> go.Figure:
    """CV PR-AUC without each feature group against the full model and its fold noise. A group carries signal when
    dropping it costs more than one fold standard deviation; the legend names both kinds, the line and the band."""
    full = check.iloc[0]
    rest = check.iloc[1:].sort_values("cv_pr_auc")
    carries = (rest.change < -full.fold_sd).to_numpy()
    fig = go.Figure()
    for mask, colour, name in ((carries, BLUE, "Carries signal: dropping it costs more than 1 fold sd"),
                               (~carries, NO_DATA, "Inside fold noise: kept, no evidence either way")):
        part = rest[mask]
        if part.empty:
            continue
        fig.add_trace(go.Bar(y=["without " + w for w in part.without], x=part.cv_pr_auc, orientation="h", name=name,
                             marker_color=colour, marker_line_width=0, text=[f"{v:.2f}" for v in part.cv_pr_auc],
                             textposition="outside", cliponaxis=False, customdata=np.stack([part.change, part.n_features], axis=1),
                             hovertemplate="%{y}: PR-AUC %{x:.3f} (%{customdata[0]:+.3f}), %{customdata[1]} features<extra></extra>"))
    fig.add_vrect(x0=full.cv_pr_auc - full.fold_sd, x1=full.cv_pr_auc + full.fold_sd, fillcolor=BLUE, opacity=0.08, line_width=0)
    fig.add_vline(x=full.cv_pr_auc, line_color=INK, line_dash="dot")
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", line=dict(color=INK, dash="dot"),
                             name=f"All features: {full.cv_pr_auc:.2f}"))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=12, color="rgba(42,120,214,0.15)"),
                             name=f"Fold noise: {full.fold_sd:.2f} each side"))
    _layout(fig, title, height=max(400, 26 * len(rest) + 170), barmode="overlay")
    fig.update_layout(legend=dict(y=-0.22))
    right = max(float(rest.cv_pr_auc.max()), float(full.cv_pr_auc + full.fold_sd))
    fig.update_xaxes(title="5-fold CV PR-AUC, training years", gridcolor=GRID, range=[0, right * 1.18])
    fig.update_yaxes(showgrid=False, categoryorder="array", categoryarray=["without " + w for w in rest.without])
    return fig


def coefficient_chart(coefficients: pd.Series, title: str, top: int = 12) -> go.Figure:
    """Largest coefficients of the final logistic regression: blue raises the odds of a multi-fatality crash,
    orange lowers them. Inputs are 0/1 flags and one-hot columns, so sizes are comparable."""
    picked = coefficients.reindex(coefficients.abs().sort_values(ascending=False).index[:top]).sort_values()
    fig = go.Figure(go.Bar(y=[feature_label(f) for f in picked.index], x=picked.values, orientation="h",
                           marker_color=np.where(picked.values >= 0, BLUE, ORANGE), marker_line_width=0,
                           text=[f"{v:+.2f}" for v in picked.values], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{x:+.2f}<extra></extra>", name="Coefficient"))
    _layout(fig, title, height=max(340, 26 * len(picked) + 120))
    lo, hi = min(float(picked.min()), 0.0), max(float(picked.max()), 0.0)
    pad = 0.3 * max(abs(lo), abs(hi), 0.1)
    fig.update_xaxes(title="Coefficient (log-odds)", gridcolor=GRID, zeroline=True, zerolinecolor="#c3c2b7",
                     range=[lo - pad if lo < 0 else 0, hi + pad])
    fig.update_yaxes(showgrid=False)
    return fig


def before_after_chart(table: pd.DataFrame, title: str) -> go.Figure:
    """The one fill, before and after on the same axes: grey is the data as received, blue after the fill."""
    fig = go.Figure()
    fig.add_trace(go.Bar(x=table.index, y=table.before, name="Before the fill (as received)", marker_color=NO_DATA,
                         marker_line_width=0, text=table.before, textposition="outside", cliponaxis=False,
                         hovertemplate="%{x}: %{y} crashes<extra>Before</extra>"))
    fig.add_trace(go.Bar(x=table.index, y=table.after, name="After the fill (deaths = 1 where only 'died' was stated)",
                         marker_color=BLUE, marker_line_width=0, text=table.after, textposition="outside", cliponaxis=False,
                         hovertemplate="%{x}: %{y} crashes<extra>After</extra>"))
    _layout(fig, title, height=380, barmode="group", bargap=0.3, bargroupgap=0.08)
    fig.update_layout(legend=dict(y=-0.28))
    fig.update_yaxes(rangemode="tozero", gridcolor=GRID, title="Fatal crashes")
    fig.update_xaxes(title="Deaths per crash", showgrid=False)
    return fig
