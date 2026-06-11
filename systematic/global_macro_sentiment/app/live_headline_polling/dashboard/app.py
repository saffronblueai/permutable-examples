from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pycountry
import requests
from config import settings
from dash import Dash, Input, Output, callback, dcc, html

COUNTRY_COLORS = px.colors.qualitative.Set2
SCORE_COLORS = {"directional": "#58d68d", "semantic": "#f194c8"}
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

app = Dash(__name__, title="GMSI Headline Monitor")
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


def resample_frequency(df: pd.DataFrame) -> str:
    span_hours = (df["publication_time"].max() - df["publication_time"].min()).total_seconds() / 3600
    if span_hours >= 120:
        return "2h"
    if span_hours >= 48:
        return "1h"
    return "30min"


def build_score_timeline(df: pd.DataFrame, title: str) -> go.Figure:
    if df.empty:
        return empty_fig(height=380)

    freq = resample_frequency(df)
    indexed = df.set_index("publication_time").sort_index()
    trend = indexed.resample(freq).agg(
        directional=("directional_score", "mean"),
        semantic=("semantic_sentiment_score", "mean"),
        headlines=("directional_score", "count"),
    )
    trend[["directional", "semantic"]] = trend[["directional", "semantic"]].rolling(3, min_periods=1).mean()

    fig = go.Figure()
    fig.add_trace(
        go.Scattergl(
            x=df["publication_time"],
            y=df["directional_score"],
            mode="markers",
            marker={"size": 4, "color": "#9aa4b2", "opacity": 0.18},
            name="Headline directional scores",
            hovertemplate="%{x|%b %-d %H:%M}<br>Directional: %{y:+.3f}<extra></extra>",
            showlegend=False,
        )
    )
    for column, label, dash in [("directional", "Directional trend", "solid"), ("semantic", "Semantic trend", "dash")]:
        fig.add_trace(
            go.Scatter(
                x=trend.index,
                y=trend[column],
                mode="lines",
                line={"color": SCORE_COLORS["directional" if column == "directional" else "semantic"], "width": 3, "dash": dash},
                name=label,
                hovertemplate="%{x|%b %-d %H:%M}<br>%{y:+.3f}<extra></extra>",
            )
        )
    fig.add_hline(y=0, line_dash="dot", line_color="#666", line_width=1)
    fig.update_layout(
        **THEME,
        title=f"{title}  |  raw points + {freq} smoothed trend",
        xaxis_title="Time (UTC)",
        yaxis_title="Score [-1, +1]",
        yaxis={"range": [-1.05, 1.05], "gridcolor": "#2e2e45"},
        xaxis={"gridcolor": "#2e2e45"},
        legend=LEGEND_TOP,
        height=380,
        margin={"l": 56, "r": 24, "t": 76, "b": 48},
    )
    return fig


def build_volume(df: pd.DataFrame, title: str) -> go.Figure:
    if df.empty:
        return empty_fig("No headline volume", height=260)
    counts = df.assign(hour=df["publication_time"].dt.floor("1h")).groupby(["hour", "country"]).size().reset_index(name="n")
    countries = sorted(counts["country"].unique())
    fig = go.Figure()
    for i, country in enumerate(countries):
        sub = counts[counts["country"] == country]
        fig.add_trace(go.Bar(x=sub["hour"], y=sub["n"], name=country, marker_color=COUNTRY_COLORS[i % len(COUNTRY_COLORS)]))
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
    map_df = df.groupby("country", as_index=False).agg(
        directional_score=("directional_score", "mean"),
        headlines=("directional_score", "count"),
    )
    map_df = add_country_metadata(map_df)
    if map_df.empty:
        return empty_fig("No mappable countries", height=430)
    fig = px.choropleth(
        map_df,
        locations="iso3",
        locationmode="ISO-3",
        color="directional_score",
        hover_name="country_name",
        hover_data={"country": True, "iso3": False, "directional_score": ":.3f", "headlines": ":,"},
        color_continuous_scale=[[0, "#c0392b"], [0.5, "#2a2a3e"], [1, "#2ecc71"]],
        range_color=[-1, 1],
        title=title,
        labels={"directional_score": "Directional"},
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
    country_df = (
        df.groupby("country")
        .agg(
            directional=("directional_score", "mean"),
            semantic=("semantic_sentiment_score", "mean"),
            headlines=("directional_score", "count"),
        )
        .sort_values("directional")
        .reset_index()
    )
    if country_df.empty:
        return empty_fig(height=360)
    fig = go.Figure()
    fig.add_trace(go.Bar(y=country_df["country"], x=country_df["directional"], orientation="h", name="Directional", marker_color=SCORE_COLORS["directional"]))
    fig.add_trace(go.Bar(y=country_df["country"], x=country_df["semantic"], orientation="h", name="Semantic", marker_color=SCORE_COLORS["semantic"]))
    fig.add_vline(x=0, line_color="#666", line_dash="dot", line_width=1)
    fig.update_layout(
        **THEME,
        title=title,
        barmode="group",
        xaxis_title="Mean score",
        xaxis={"range": [-1.05, 1.05], "gridcolor": "#2e2e45"},
        legend=LEGEND_BOTTOM,
        height=max(360, 150 + len(country_df) * 44),
        margin={"l": 72, "r": 24, "t": 64, "b": 88},
    )
    return fig


def build_topic_bars(df: pd.DataFrame, title: str, top_n: int = 12) -> go.Figure:
    top_topics = df.groupby("topic").size().nlargest(top_n).index
    topic_df = (
        df[df["topic"].isin(top_topics)]
        .groupby("topic")
        .agg(directional=("directional_score", "mean"), headlines=("directional_score", "count"))
        .sort_values("directional")
        .reset_index()
    )
    if topic_df.empty:
        return empty_fig(height=360)
    fig = go.Figure(go.Bar(
        x=topic_df["directional"],
        y=topic_df["topic"],
        orientation="h",
        marker_color=["#e74c3c" if value < 0 else "#2ecc71" for value in topic_df["directional"]],
        customdata=topic_df[["headlines"]],
        hovertemplate="%{y}<br>Directional: %{x:+.3f}<br>Headlines: %{customdata[0]:,}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#666", line_dash="dot", line_width=1)
    fig.update_layout(
        **THEME,
        title=title,
        xaxis_title="Mean directional score",
        xaxis={"range": [-1.05, 1.05], "gridcolor": "#2e2e45"},
        height=max(330, 100 + len(topic_df) * 34),
        margin={"l": 12, "r": 24, "t": 56, "b": 44},
    )
    return fig


def build_distribution(df: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=df["directional_score"], name="Directional", marker_color=SCORE_COLORS["directional"], opacity=0.78, nbinsx=32))
    fig.add_trace(go.Histogram(x=df["semantic_sentiment_score"], name="Semantic", marker_color=SCORE_COLORS["semantic"], opacity=0.68, nbinsx=32))
    fig.update_layout(
        **THEME,
        title=title,
        barmode="overlay",
        xaxis_title="Score",
        yaxis_title="Headlines",
        xaxis={"range": [-1.05, 1.05], "gridcolor": "#2e2e45"},
        yaxis={"gridcolor": "#2e2e45"},
        legend=LEGEND_BOTTOM,
        height=360,
        margin={"l": 56, "r": 24, "t": 64, "b": 88},
    )
    return fig


def build_layout() -> html.Div:
    country_options = [{"label": "All countries", "value": ALL}] + [{"label": c, "value": c} for c in settings.countries_list]
    topic_options = [{"label": "All topics", "value": ALL}] + [{"label": t, "value": t} for t in settings.topics_list]
    return html.Div(
        [
            html.Div(
                [
                    html.Div([
                        html.H1("GMSI Headline Monitor", style={"margin": "0", "color": "#fff", "fontSize": "20px"}),
                        html.P("Permutable AI · Global Macro Sentiment Indices · Raw Headlines", style={"margin": "2px 0 0", "color": "#aaa", "fontSize": "12px"}),
                    ]),
                    html.Div([
                        dcc.Dropdown(id="country-dropdown", options=country_options, value=ALL, clearable=False, style=DROPDOWN_STYLE),
                        dcc.Dropdown(id="topic-dropdown", options=topic_options, value=ALL, clearable=False, style={**DROPDOWN_STYLE, "minWidth": "360px"}),
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
    Input("interval", "n_intervals"),
)
def update_content(selected_country: str, selected_topic: str, n: int):
    ts_label = datetime.now(timezone.utc).strftime("Last updated: %Y-%m-%d %H:%M UTC")
    params = {"hours": LOOKBACK_HOURS, "limit": 50000}
    if selected_country != ALL:
        params["country"] = selected_country
    if selected_topic != ALL:
        params["topic"] = selected_topic

    data = fetch_json("/headlines", params)
    if not data:
        return [html.P("No data available - waiting for poller...", style={"color": "#888"})], ts_label

    df = pd.DataFrame(data)
    df["publication_time"] = pd.to_datetime(df["publication_time"], utc=True)
    df = df.sort_values("publication_time")
    df["directional_score"] = pd.to_numeric(df["directional_score"], errors="coerce")
    df["semantic_sentiment_score"] = pd.to_numeric(df["semantic_sentiment_score"], errors="coerce")
    df = df.dropna(subset=["directional_score", "semantic_sentiment_score"])

    if df.empty:
        return [html.P("No scored headline data available.", style={"color": "#888"})], ts_label

    scope = selected_country if selected_country != ALL else "All Countries"
    if selected_topic != ALL:
        scope += f" · {selected_topic}"

    directional_mean = df["directional_score"].mean()
    semantic_mean = df["semantic_sentiment_score"].mean()
    divergence = directional_mean - semantic_mean
    stat_row = html.Div(
        [
            stat_card("Headlines (7d)", f"{len(df):,}"),
            stat_card("Mean Directional", f"{directional_mean:+.3f}", score_color(directional_mean)),
            stat_card("Mean Semantic", f"{semantic_mean:+.3f}", score_color(semantic_mean)),
            stat_card("Directional - Semantic", f"{divergence:+.3f}", score_color(divergence)),
            stat_card("Countries", str(df["country"].nunique())),
        ],
        style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "20px"},
    )

    cell = {"flex": "1 1 45%", "minWidth": "420px"}
    return [
        stat_row,
        dcc.Graph(config={"displayModeBar": False}, figure=build_score_timeline(df, f"{scope} — Directional vs Semantic Sentiment"), style={"marginBottom": "16px"}),
        dcc.Graph(config={"displayModeBar": False}, figure=build_volume(df, f"{scope} — Headline Count per Hour"), style={"marginBottom": "24px"}),
        html.Div(
            [
                dcc.Graph(config={"displayModeBar": False}, figure=build_map(df, f"{scope} — Mean Directional Sentiment by Country"), style=cell),
                dcc.Graph(config={"displayModeBar": False}, figure=build_topic_bars(df, f"{scope} — Directional Sentiment by Topic"), style=cell),
                dcc.Graph(config={"displayModeBar": False}, figure=build_distribution(df, f"{scope} — Score Distribution"), style=cell),
                dcc.Graph(config={"displayModeBar": False}, figure=build_country_bars(df, f"{scope} — Directional vs Semantic by Country"), style=cell),
            ],
            style={"display": "flex", "flexWrap": "wrap", "gap": "16px"},
        ),
    ], ts_label


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
