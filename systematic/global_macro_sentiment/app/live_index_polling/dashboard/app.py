from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pycountry
import requests
from config import settings
from dash import Dash, Input, Output, callback, dcc, html

COUNTRY_COLORS = px.colors.qualitative.Set2
SCORE_COLORS = {"directional": "#58d68d", "semantic_sentiment": "#f194c8"}
THEME = {
    "template": "plotly_dark",
    "paper_bgcolor": "#1a1a2e",
    "plot_bgcolor": "#1a1a2e",
    "font": {"color": "#e5e7eb", "size": 12},
}
CARD_STYLE = {
    "background": "#1e1e30",
    "border": "1px solid #2e2e45",
    "borderRadius": "10px",
    "padding": "16px 20px",
    "flex": "1",
    "minWidth": "140px",
    "textAlign": "center",
}
DROPDOWN_STYLE = {"color": "#000", "fontSize": "13px", "minWidth": "220px"}
LEGEND_TOP = {"orientation": "h", "x": 0, "y": 1.08, "xanchor": "left", "yanchor": "bottom"}
LEGEND_BOTTOM = {"orientation": "h", "x": 0, "y": -0.24, "xanchor": "left", "yanchor": "top"}
ALL = "ALL"
LOOKBACK_HOURS = 168
ROLLING_HOURS = 5

app = Dash(__name__, title="GMSI Index Monitor")
app.index_string = """
<!DOCTYPE html>
<html>
    <head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}<style>html, body { margin: 0; background: #12121f; }</style></head>
    <body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>
"""


def fetch_json(path: str, params: dict | None = None) -> list | dict | None:
    try:
        response = requests.get(f"{settings.api_url}{path}", params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def empty_fig(message: str = "No data - waiting for poller...", height: int = 300) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"size": 14, "color": "#888"},
    )
    fig.update_layout(**THEME, height=height, margin={"l": 24, "r": 24, "t": 48, "b": 32})
    return fig


def stat_card(label: str, value: str, color: str = "#ccc") -> html.Div:
    return html.Div(
        [
            html.Div(
                label,
                style={
                    "color": "#888",
                    "fontSize": "11px",
                    "marginBottom": "6px",
                    "textTransform": "uppercase",
                    "letterSpacing": "0.05em",
                },
            ),
            html.Div(value, style={"color": color, "fontSize": "22px", "fontWeight": "700"}),
        ],
        style=CARD_STYLE,
    )


def score_color(value: float) -> str:
    if pd.isna(value):
        return "#95a5a6"
    if value > 0.05:
        return "#2ecc71"
    if value < -0.05:
        return "#e74c3c"
    return "#95a5a6"


def country_meta(country: str) -> tuple[str | None, str]:
    record = pycountry.countries.get(alpha_2=str(country).upper())
    if record is None:
        return None, str(country).upper()
    return record.alpha_3, record.name


def add_country_metadata(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    metadata = {country: country_meta(country) for country in out["country"].dropna().unique()}
    out["iso3"] = out["country"].map(lambda country: metadata.get(country, (None, country))[0])
    out["country_name"] = out["country"].map(lambda country: metadata.get(country, (None, country))[1])
    return out.dropna(subset=["iso3"])


def add_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["headline_count"] = pd.to_numeric(out["headline_count"], errors="coerce").fillna(0)
    out["sentiment_sum"] = pd.to_numeric(out["sentiment_sum"], errors="coerce")
    out["sentiment_abs_sum"] = pd.to_numeric(out["sentiment_abs_sum"], errors="coerce")
    out["sentiment_avg"] = out["sentiment_sum"] / out["headline_count"].where(out["headline_count"] != 0)
    out["activity_weighted"] = out["sentiment_sum"] / out["sentiment_abs_sum"].where(out["sentiment_abs_sum"] != 0)
    return out.dropna(subset=["sentiment_avg"])


def aggregate_signal(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby(["publication_time", "sentiment_type"], as_index=False).agg(
        sentiment_sum=("sentiment_sum", "sum"),
        sentiment_abs_sum=("sentiment_abs_sum", "sum"),
        headline_count=("headline_count", "sum"),
    )
    grouped = add_metrics(grouped).sort_values(["sentiment_type", "publication_time"])
    grouped["sentiment_smooth"] = grouped.groupby("sentiment_type")["sentiment_avg"].transform(
        lambda values: values.rolling(ROLLING_HOURS, min_periods=1).mean()
    )
    return grouped


def latest_country_scores(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby(["country", "sentiment_type", "publication_time"], as_index=False).agg(
        sentiment_sum=("sentiment_sum", "sum"),
        sentiment_abs_sum=("sentiment_abs_sum", "sum"),
        headline_count=("headline_count", "sum"),
    )
    scored = add_metrics(grouped)
    if scored.empty:
        return scored
    return scored.sort_values("publication_time").groupby(["country", "sentiment_type"], as_index=False).tail(1)


def build_signal_timeline(df: pd.DataFrame, title: str) -> go.Figure:
    series = aggregate_signal(df)
    if series.empty:
        return empty_fig(height=380)
    fig = go.Figure()
    labels = {"directional": "Directional", "semantic_sentiment": "Semantic"}
    for sentiment_type, label in labels.items():
        sub = series[series["sentiment_type"] == sentiment_type]
        if sub.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=sub["publication_time"],
                y=sub["sentiment_smooth"],
                mode="lines+markers",
                line={"color": SCORE_COLORS[sentiment_type], "width": 3, "dash": "dash" if sentiment_type == "semantic_sentiment" else "solid"},
                marker={"size": 4},
                name=f"{label} {ROLLING_HOURS}h avg",
                hovertemplate="%{x|%b %-d %H:%M}<br>%{y:+.3f}<extra></extra>",
            )
        )
    fig.add_hline(y=0, line_dash="dot", line_color="#666", line_width=1)
    fig.update_layout(
        **THEME,
        title=title,
        xaxis_title="Time (UTC)",
        yaxis_title="Headline-weighted sentiment avg [-1, +1]",
        yaxis={"range": [-1.05, 1.05], "gridcolor": "#2e2e45"},
        xaxis={"gridcolor": "#2e2e45"},
        legend=LEGEND_TOP,
        height=380,
        margin={"l": 56, "r": 24, "t": 76, "b": 48},
    )
    return fig


def build_volume(df: pd.DataFrame, title: str) -> go.Figure:
    counts = df[df["sentiment_type"] == "directional"].groupby(["publication_time", "country"], as_index=False)["headline_count"].sum()
    if counts.empty:
        return empty_fig("No headline volume", height=260)
    fig = go.Figure()
    for i, country in enumerate(sorted(counts["country"].unique())):
        sub = counts[counts["country"] == country]
        fig.add_trace(go.Bar(x=sub["publication_time"], y=sub["headline_count"], name=country, marker_color=COUNTRY_COLORS[i % len(COUNTRY_COLORS)]))
    fig.update_layout(
        **THEME,
        barmode="stack",
        title=title,
        xaxis_title="Time (UTC)",
        yaxis_title="Headlines",
        legend=LEGEND_TOP,
        height=260,
        margin={"l": 56, "r": 24, "t": 72, "b": 44},
        xaxis={"gridcolor": "#2e2e45"},
        yaxis={"gridcolor": "#2e2e45"},
    )
    return fig


def build_map(df: pd.DataFrame, title: str) -> go.Figure:
    latest = latest_country_scores(df[df["sentiment_type"] == "directional"])
    latest = add_country_metadata(latest)
    if latest.empty:
        return empty_fig("No mappable countries", height=430)
    fig = px.choropleth(
        latest,
        locations="iso3",
        locationmode="ISO-3",
        color="sentiment_avg",
        hover_name="country_name",
        hover_data={"country": True, "iso3": False, "sentiment_avg": ":.3f", "headline_count": ":,"},
        color_continuous_scale=[[0, "#c0392b"], [0.5, "#2a2a3e"], [1, "#2ecc71"]],
        range_color=[-1, 1],
        title=title,
        labels={"sentiment_avg": "Directional"},
    )
    fig.update_layout(
        **THEME,
        geo={
            "showframe": False,
            "showcoastlines": True,
            "coastlinecolor": "#444",
            "showland": True,
            "landcolor": "#2a2a3e",
            "showocean": True,
            "oceancolor": "#1a1a2e",
            "showcountries": True,
            "countrycolor": "#333",
            "bgcolor": "#1a1a2e",
            "projection_type": "natural earth",
        },
        height=430,
        margin={"l": 0, "r": 0, "t": 56, "b": 0},
        coloraxis_colorbar={"title": "Directional", "tickfont": {"color": "#ccc"}, "len": 0.72, "thickness": 14},
    )
    return fig


def build_country_bars(df: pd.DataFrame, title: str) -> go.Figure:
    latest = latest_country_scores(df)
    if latest.empty:
        return empty_fig(height=360)
    order = latest.groupby("country")["sentiment_avg"].mean().sort_values().index.tolist()
    fig = go.Figure()
    labels = {"directional": "Directional", "semantic_sentiment": "Semantic"}
    for sentiment_type, label in labels.items():
        sub = latest[latest["sentiment_type"] == sentiment_type]
        fig.add_trace(go.Bar(y=sub["country"], x=sub["sentiment_avg"], orientation="h", name=label, marker_color=SCORE_COLORS[sentiment_type]))
    fig.add_vline(x=0, line_color="#666", line_dash="dot", line_width=1)
    fig.update_layout(
        **THEME,
        title=title,
        barmode="group",
        xaxis_title="Latest sentiment avg",
        yaxis={"categoryorder": "array", "categoryarray": order},
        xaxis={"range": [-1.05, 1.05], "gridcolor": "#2e2e45"},
        legend=LEGEND_BOTTOM,
        height=max(360, 150 + len(order) * 44),
        margin={"l": 72, "r": 24, "t": 64, "b": 88},
    )
    return fig


def build_heatmap(df: pd.DataFrame, title: str) -> go.Figure:
    scored = add_metrics(df[df["sentiment_type"] == "directional"])
    if scored.empty:
        return empty_fig("Not enough data for heatmap", height=330)
    scored = scored.sort_values(["country", "publication_time"])
    scored["sentiment_smooth"] = scored.groupby("country")["sentiment_avg"].transform(lambda values: values.rolling(ROLLING_HOURS, min_periods=1).mean())
    pivot = scored.pivot_table(index="publication_time", columns="country", values="sentiment_smooth", aggfunc="mean").sort_index()
    if pivot.empty:
        return empty_fig("Not enough data for heatmap", height=330)
    fig = go.Figure(go.Heatmap(
        z=pivot.values.T,
        x=pivot.index,
        y=pivot.columns,
        colorscale=[[0, "#c0392b"], [0.5, "#2a2a3e"], [1, "#2ecc71"]],
        zmid=0,
        zmin=-1,
        zmax=1,
        colorbar={"title": "Directional", "tickfont": {"color": "#ccc"}, "len": 0.72, "thickness": 14},
        hovertemplate="%{y} · %{x|%b %-d %H:%M}<br>Directional: %{z:+.3f}<extra></extra>",
    ))
    fig.update_layout(
        **THEME,
        title=title,
        xaxis_title="Time (UTC)",
        yaxis_title="Country",
        height=max(330, 140 + len(pivot.columns) * 44),
        margin={"l": 64, "r": 80, "t": 56, "b": 72},
    )
    return fig


def build_topic_bars(df: pd.DataFrame, title: str, top_n: int = 12) -> go.Figure:
    scored = add_metrics(df[df["sentiment_type"] == "directional"])
    top_topics = scored.groupby("topic")["headline_count"].sum().nlargest(top_n).index
    topic_df = (
        scored[scored["topic"].isin(top_topics)]
        .groupby("topic")
        .agg(sentiment_avg=("sentiment_avg", "mean"), headlines=("headline_count", "sum"))
        .sort_values("sentiment_avg")
        .reset_index()
    )
    if topic_df.empty:
        return empty_fig(height=360)
    fig = go.Figure(go.Bar(
        x=topic_df["sentiment_avg"],
        y=topic_df["topic"],
        orientation="h",
        marker_color=["#e74c3c" if value < 0 else "#2ecc71" for value in topic_df["sentiment_avg"]],
        customdata=topic_df[["headlines"]],
        hovertemplate="%{y}<br>Directional: %{x:+.3f}<br>Headlines: %{customdata[0]:,}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#666", line_dash="dot", line_width=1)
    fig.update_layout(
        **THEME,
        title=title,
        xaxis_title="Mean directional sentiment avg",
        xaxis={"range": [-1.05, 1.05], "gridcolor": "#2e2e45"},
        height=max(330, 100 + len(topic_df) * 34),
        margin={"l": 12, "r": 24, "t": 56, "b": 44},
    )
    return fig


def build_layout() -> html.Div:
    country_options = [{"label": "All countries", "value": ALL}] + [{"label": c, "value": c} for c in settings.countries_list]
    topic_options = [{"label": "All topics", "value": ALL}] + [{"label": t, "value": t} for t in settings.topics_list]
    index_options = [
        {"label": "Combined", "value": "COMBINED"},
        {"label": "Domestic", "value": "DOMESTIC"},
        {"label": "International", "value": "INTERNATIONAL"},
    ]
    return html.Div(
        [
            html.Div(
                [
                    html.Div([
                        html.H1("GMSI Index Monitor", style={"margin": "0", "color": "#fff", "fontSize": "20px"}),
                        html.P("Permutable AI · Global Macro Sentiment Indices · Hourly Index", style={"margin": "2px 0 0", "color": "#aaa", "fontSize": "12px"}),
                    ]),
                    html.Div([
                        dcc.Dropdown(id="country-dropdown", options=country_options, value=ALL, clearable=False, style=DROPDOWN_STYLE),
                        dcc.Dropdown(id="topic-dropdown", options=topic_options, value=ALL, clearable=False, style={**DROPDOWN_STYLE, "minWidth": "360px"}),
                        dcc.Dropdown(id="index-type-dropdown", options=index_options, value="COMBINED", clearable=False, style={**DROPDOWN_STYLE, "minWidth": "160px"}),
                    ], style={"display": "flex", "gap": "12px", "alignItems": "center", "flexWrap": "wrap"}),
                ],
                style={
                    "background": "#0f0f1a",
                    "padding": "16px 32px",
                    "borderBottom": "2px solid #222",
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "space-between",
                    "gap": "24px",
                    "flexWrap": "wrap",
                },
            ),
            html.Div(id="main-content", style={"padding": "24px 32px"}),
            dcc.Interval(id="interval", interval=settings.refresh_interval_ms, n_intervals=0),
            html.Div(id="last-updated", style={"textAlign": "right", "color": "#555", "fontSize": "11px", "padding": "0 32px 12px"}),
        ],
        style={"background": "#12121f", "minHeight": "100vh", "fontFamily": "Inter, sans-serif"},
    )


app.layout = build_layout()


@callback(
    Output("main-content", "children"),
    Output("last-updated", "children"),
    Input("country-dropdown", "value"),
    Input("topic-dropdown", "value"),
    Input("index-type-dropdown", "value"),
    Input("interval", "n_intervals"),
)
def update_content(selected_country: str, selected_topic: str, index_type: str, n: int):
    ts_label = datetime.now(timezone.utc).strftime("Last updated: %Y-%m-%d %H:%M UTC")
    params = {"hours": LOOKBACK_HOURS, "limit": 50000, "index_type": index_type}
    if selected_country != ALL:
        params["country"] = selected_country
    if selected_topic != ALL:
        params["topic"] = selected_topic

    data = fetch_json("/gmsi", params)
    if not data:
        return [html.P("No data available - waiting for poller...", style={"color": "#888"})], ts_label

    df = pd.DataFrame(data)
    df["publication_time"] = pd.to_datetime(df["publication_time"], utc=True)
    df = df.sort_values("publication_time")
    scored = add_metrics(df)

    if scored.empty:
        return [html.P("No scored index data available.", style={"color": "#888"})], ts_label

    scope = selected_country if selected_country != ALL else "All Countries"
    if selected_topic != ALL:
        scope += f" · {selected_topic}"
    scope += f" · {index_type}"

    directional = scored[scored["sentiment_type"] == "directional"]
    semantic = scored[scored["sentiment_type"] == "semantic_sentiment"]
    mean_dir = directional["sentiment_avg"].mean()
    mean_sem = semantic["sentiment_avg"].mean()
    total_headlines = int(directional["headline_count"].sum())
    latest_time = scored["publication_time"].max().strftime("%Y-%m-%d %H:%M UTC")

    stat_row = html.Div(
        [
            stat_card("Headlines (7d)", f"{total_headlines:,}"),
            stat_card("Mean Directional", f"{mean_dir:+.3f}", score_color(mean_dir)),
            stat_card("Mean Semantic", f"{mean_sem:+.3f}", score_color(mean_sem)),
            stat_card("Directional - Semantic", f"{mean_dir - mean_sem:+.3f}", score_color(mean_dir - mean_sem)),
            stat_card("Latest Hour", latest_time),
        ],
        style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "20px"},
    )

    cell = {"flex": "1 1 45%", "minWidth": "420px"}
    return [
        stat_row,
        dcc.Graph(config={"displayModeBar": False}, figure=build_signal_timeline(df, f"{scope} — Directional vs Semantic Sentiment"), style={"marginBottom": "16px"}),
        dcc.Graph(config={"displayModeBar": False}, figure=build_volume(df, f"{scope} — Hourly Headline Count"), style={"marginBottom": "24px"}),
        html.Div(
            [
                dcc.Graph(config={"displayModeBar": False}, figure=build_map(df, f"{scope} — Latest Directional Sentiment by Country"), style=cell),
                dcc.Graph(config={"displayModeBar": False}, figure=build_topic_bars(df, f"{scope} — Directional Sentiment by Topic"), style=cell),
                dcc.Graph(config={"displayModeBar": False}, figure=build_heatmap(df, f"{scope} — Country Sentiment Heatmap"), style=cell),
                dcc.Graph(config={"displayModeBar": False}, figure=build_country_bars(df, f"{scope} — Directional vs Semantic by Country"), style=cell),
            ],
            style={"display": "flex", "flexWrap": "wrap", "gap": "16px"},
        ),
    ], ts_label


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
