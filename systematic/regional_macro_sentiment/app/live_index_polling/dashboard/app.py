from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from config import settings
from dash import Dash, Input, Output, callback, dcc, html

# ── Colour palette ─────────────────────────────────────────────────────────────
COUNTRY_COLORS = px.colors.qualitative.Set2
_CHART_BASE = dict(template="plotly_dark", paper_bgcolor="#1a1a2e", plot_bgcolor="#1a1a2e")
_LEGEND = dict(x=1.01, xanchor="left", y=1, yanchor="top")
_CARD_STYLE = {
    "background": "#1e1e30",
    "border": "1px solid #2e2e45",
    "borderRadius": "10px",
    "padding": "16px 20px",
    "flex": "1",
    "minWidth": "120px",
    "textAlign": "center",
}
_LABEL_STYLE = {
    "color": "#888", "fontSize": "11px", "marginBottom": "4px",
    "textTransform": "uppercase", "letterSpacing": "0.05em",
}
_DROPDOWN_STYLE = {"color": "#000", "fontSize": "13px", "minWidth": "200px"}
_FILTER_BAR = {
    "background": "#0f0f1a",
    "padding": "10px 32px",
    "borderBottom": "1px solid #1e1e30",
    "display": "flex",
    "alignItems": "flex-end",
    "gap": "16px",
}

ALL = "ALL"
ROLLING_WINDOW = 5  # hours for sentiment rolling mean

# ── Country group definitions ───────────────────────────────────────────────────
COUNTRY_GROUPS: dict[str, list[str]] = {
    "G7": [
        "canada", "france", "germany", "italy", "japan",
        "united kingdom", "united states",
    ],
    "G20": [
        "argentina", "australia", "brazil", "canada", "china", "france", "germany",
        "india", "indonesia", "italy", "japan", "mexico", "russia", "saudi arabia",
        "south africa", "south korea", "turkey", "united kingdom", "united states",
    ],
    "Europe": [
        "austria", "belgium", "bulgaria", "croatia", "czech republic", "denmark",
        "estonia", "finland", "france", "germany", "greece", "hungary", "ireland",
        "italy", "latvia", "lithuania", "luxembourg", "malta", "netherlands", "norway",
        "poland", "portugal", "romania", "slovakia", "slovenia", "spain", "sweden",
        "switzerland", "ukraine", "united kingdom",
    ],
    "Asia": [
        "bangladesh", "cambodia", "china", "hong kong", "india", "indonesia", "japan",
        "malaysia", "mongolia", "myanmar", "pakistan", "philippines", "singapore",
        "south korea", "sri lanka", "taiwan", "thailand", "vietnam",
    ],
    "North America": ["canada", "mexico", "united states"],
    "South America": [
        "argentina", "bolivia", "brazil", "chile", "colombia", "ecuador",
        "paraguay", "peru", "uruguay", "venezuela",
    ],
    "Africa": [
        "algeria", "angola", "egypt", "ethiopia", "ghana", "kenya", "morocco",
        "mozambique", "nigeria", "senegal", "south africa", "tanzania", "tunisia",
        "zimbabwe",
    ],
    "Middle East": [
        "bahrain", "iran", "iraq", "israel", "jordan", "kuwait", "lebanon",
        "oman", "qatar", "saudi arabia", "turkey", "united arab emirates",
    ],
}

_GROUP_OPTIONS = [{"label": k, "value": k} for k in COUNTRY_GROUPS]

_INDEX_TYPE_OPTIONS = [
    {"label": "Combined",      "value": "COMBINED"},
    {"label": "Domestic",      "value": "DOMESTIC"},
    {"label": "International", "value": "INTERNATIONAL"},
]


# ── App ────────────────────────────────────────────────────────────────────────
app = Dash(__name__, title="Regional Macro Sentiment Monitor")


# ── Helpers ────────────────────────────────────────────────────────────────────

def fetch_json(path: str, params: dict | None = None) -> list | dict | None:
    try:
        r = requests.get(f"{settings.api_url}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _empty_fig(message: str = "No data — waiting for poller…", height: int = 300) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=14, color="#888"),
    )
    fig.update_layout(**_CHART_BASE, height=height, margin=dict(l=0, r=0, t=40, b=20))
    return fig


def _stat_card(label: str, value: str, color: str = "#ccc") -> html.Div:
    return html.Div(
        [
            html.Div(label, style={
                "color": "#888", "fontSize": "11px", "marginBottom": "6px",
                "textTransform": "uppercase", "letterSpacing": "0.05em",
            }),
            html.Div(value, style={"color": color, "fontSize": "22px", "fontWeight": "700"}),
        ],
        style=_CARD_STYLE,
    )


def _sentiment_color(v: float) -> str:
    if v >= settings.upper_threshold:
        return "#2ecc71"
    if v <= settings.lower_threshold:
        return "#e74c3c"
    return "#95a5a6"


def _filter_by_country_group(df: pd.DataFrame, group: str) -> tuple[pd.DataFrame, list[str]]:
    """Return df and active_countries restricted to the selected country group."""
    group_members = {c.lower() for c in COUNTRY_GROUPS.get(group, [])}
    all_in_data = sorted(df["country"].dropna().unique().tolist())
    active = [c for c in all_in_data if c.lower() in group_members]
    filtered = df[df["country"].str.lower().isin(group_members)]
    return filtered, active


def _rolling_sentiment(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to (country, hour), compute mean sentiment_avg and 5h rolling mean."""
    agg = (
        df.groupby(["country", "publication_time"])
        .agg(
            sentiment_avg=("sentiment_avg", "mean"),
            sentiment_sum=("sentiment_sum", "sum"),
            headline_count=("headline_count", "sum"),
            sentiment_std=("sentiment_std", "mean"),
        )
        .reset_index()
        .sort_values(["country", "publication_time"])
    )
    agg["sentiment_smooth"] = agg.groupby("country")["sentiment_avg"].transform(
        lambda x: x.rolling(ROLLING_WINDOW, min_periods=1).mean()
    )
    return agg


# ── Chart builders ─────────────────────────────────────────────────────────────

def _build_world_map(df: pd.DataFrame, title: str) -> go.Figure:
    """Choropleth world map — most-recent sentiment_avg per country (topic pre-filtered)."""
    map_df = (
        df.sort_values("publication_time")
        .groupby("country")["sentiment_avg"]
        .last()
        .reset_index()
    )
    if map_df.empty:
        return _empty_fig("No map data", height=420)

    map_df["country"] = map_df["country"].str.title()
    fig = px.choropleth(
        map_df,
        locations="country",
        locationmode="country names",
        color="sentiment_avg",
        color_continuous_scale=[[0, "#c0392b"], [0.5, "#f5f5f5"], [1, "#2ecc71"]],
        range_color=[-1, 1],
        title=title,
        labels={"sentiment_avg": "Sentiment Avg"},
    )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#1a1a2e",
        geo=dict(
            showframe=False, showcoastlines=True, coastlinecolor="#444",
            showland=True, landcolor="#2a2a3e", showocean=True, oceancolor="#1a1a2e",
            showcountries=True, countrycolor="#333", bgcolor="#1a1a2e",
            projection_type="natural earth",
        ),
        height=440,
        margin=dict(l=0, r=0, t=60, b=0),
        coloraxis_colorbar=dict(title="Sentiment", tickfont=dict(color="#ccc")),
    )
    return fig


def _build_sentiment_ts(agg: pd.DataFrame, active_countries: list[str], title: str) -> go.Figure:
    fig = go.Figure()
    for i, country in enumerate(active_countries):
        color = COUNTRY_COLORS[i % len(COUNTRY_COLORS)]
        sub = agg[agg["country"] == country].sort_values("publication_time")
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["publication_time"], y=sub["sentiment_avg"],
            mode="lines", line=dict(color=color, width=1, dash="dot"),
            name=f"{country.title()} raw", legendgroup=country, opacity=0.4,
        ))
        fig.add_trace(go.Scatter(
            x=sub["publication_time"], y=sub["sentiment_smooth"],
            mode="lines", line=dict(color=color, width=2),
            name=f"{country.title()} {ROLLING_WINDOW}h rolling", legendgroup=country,
        ))
    fig.add_hline(y=settings.upper_threshold, line_dash="dash", line_color="#2ecc71",
                  line_width=1, annotation_text="HIGH", annotation_position="right")
    fig.add_hline(y=settings.lower_threshold, line_dash="dash", line_color="#e74c3c",
                  line_width=1, annotation_text="LOW", annotation_position="right")
    fig.add_hline(y=0, line_dash="dot", line_color="#555", line_width=1)
    fig.update_layout(
        **_CHART_BASE,
        title=title,
        xaxis_title="Time (UTC)",
        yaxis_title="Sentiment Avg  [−1, +1]",
        yaxis=dict(range=[-1.05, 1.05]),
        legend=_LEGEND,
        height=380,
        margin=dict(l=0, r=160, t=60, b=40),
    )
    return fig


def _build_headline_count(agg: pd.DataFrame, active_countries: list[str], title: str) -> go.Figure:
    fig = go.Figure()
    for i, country in enumerate(active_countries):
        color = COUNTRY_COLORS[i % len(COUNTRY_COLORS)]
        sub = agg[agg["country"] == country].sort_values("publication_time")
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["publication_time"], y=sub["headline_count"],
            mode="lines", line=dict(color=color, width=2),
            name=country.title(),
        ))
    fig.update_layout(
        **_CHART_BASE,
        title=title,
        xaxis_title="Time (UTC)",
        yaxis_title="Headline Count",
        legend=_LEGEND,
        height=260,
        margin=dict(l=0, r=160, t=60, b=40),
    )
    return fig


def _build_sentiment_heatmap(agg: pd.DataFrame, active_countries: list[str], title: str) -> go.Figure:
    """5-period rolling sentiment heatmap — country × hour. NaNs filled to 0 (grey)."""
    pivot = (
        agg.pivot_table(
            index="publication_time", columns="country", values="sentiment_smooth", aggfunc="mean"
        )
        .reindex(columns=active_countries)
        .sort_index()
        .fillna(0)
    )
    if pivot.empty:
        return _empty_fig("Not enough data for heatmap", height=200)

    z = pivot.values.T
    x_labels = pivot.index.strftime("%b %d %H:%M").tolist()

    seen_dates: set = set()
    tick_positions: list[int] = []
    tick_labels: list[str] = []
    for i, t in enumerate(pivot.index):
        d = t.date()
        if d not in seen_dates:
            seen_dates.add(d)
            tick_positions.append(i)
            tick_labels.append(t.strftime("%b %d"))

    fig = go.Figure(go.Heatmap(
        z=z,
        x=x_labels,
        y=[c.title() for c in active_countries],
        colorscale=[[0.0, "#c0392b"], [0.5, "#95a5a6"], [1.0, "#2ecc71"]],
        zmid=0, zmin=-1, zmax=1,
        colorbar=dict(
            title=dict(text="Sentiment", font=dict(color="#ccc")),
            tickfont=dict(color="#ccc"), x=1.0, xanchor="left", thickness=14, len=0.75,
        ),
        hovertemplate="<b>%{y}</b> — %{x}<br>Sentiment: %{z:.3f}<extra></extra>",
    ))
    fig.update_layout(
        **_CHART_BASE,
        title=title,
        xaxis=dict(
            tickmode="array",
            tickvals=[x_labels[i] for i in tick_positions],
            ticktext=tick_labels,
            tickangle=30,
        ),
        yaxis_title="Country",
        height=max(200, len(active_countries) * 50 + 100),
        margin=dict(l=0, r=80, t=60, b=60),
    )
    return fig


def _build_topic(df: pd.DataFrame, title: str, top_n: int = 15) -> go.Figure:
    """Mean sentiment_avg by topic (top N by total headline volume)."""
    top_topics = df.groupby("topic_name")["headline_count"].sum().nlargest(top_n).index
    topic_df = (
        df[df["topic_name"].isin(top_topics)]
        .groupby("topic_name")["sentiment_avg"]
        .mean()
        .sort_values()
        .reset_index()
    )
    if topic_df.empty:
        return _empty_fig(height=340)
    fig = go.Figure(go.Bar(
        x=topic_df["sentiment_avg"],
        y=topic_df["topic_name"],
        orientation="h",
        marker_color=["#e74c3c" if v < 0 else "#2ecc71" for v in topic_df["sentiment_avg"]],
    ))
    fig.add_vline(x=0, line_color="#555", line_dash="dash", line_width=1)
    fig.update_layout(
        **_CHART_BASE,
        title=title,
        xaxis_title="Mean Sentiment Avg",
        xaxis=dict(range=[-1.05, 1.05]),
        height=max(340, len(topic_df) * 28 + 80),
        margin=dict(l=0, r=0, t=50, b=30),
    )
    return fig


# ── Layout ─────────────────────────────────────────────────────────────────────

app.layout = html.Div(
    [
        # ── Header ────────────────────────────────────────────────────────────
        html.Div(
            [
                html.H1("Regional Macro Sentiment Monitor",
                        style={"margin": "0", "color": "#fff", "fontSize": "20px"}),
                html.P("Permutable AI  ·  Live Regional Polling Application",
                       style={"margin": "2px 0 0", "color": "#aaa", "fontSize": "12px"}),
            ],
            style={
                "background": "#0f0f1a",
                "padding": "16px 32px",
                "borderBottom": "2px solid #222",
            },
        ),

        # ── Map filters ───────────────────────────────────────────────────────
        html.Div(
            [
                html.Div([
                    html.Div("Map Topic", style=_LABEL_STYLE),
                    dcc.Dropdown(
                        id="map-topic-dropdown",
                        options=[{"label": "All Topics", "value": ALL}],
                        value=ALL,
                        clearable=False,
                        style=_DROPDOWN_STYLE,
                    ),
                ]),
                html.Div([
                    html.Div("Map Index Type", style=_LABEL_STYLE),
                    dcc.Dropdown(
                        id="map-index-type-dropdown",
                        options=_INDEX_TYPE_OPTIONS,
                        value="COMBINED",
                        clearable=False,
                        style=_DROPDOWN_STYLE,
                    ),
                ]),
            ],
            style=_FILTER_BAR,
        ),

        # ── Map output ────────────────────────────────────────────────────────
        html.Div(id="map-content", style={"padding": "16px 32px 0"}),

        # ── Charts filters ────────────────────────────────────────────────────
        html.Div(
            [
                html.Div([
                    html.Div("Charts Topic", style=_LABEL_STYLE),
                    dcc.Dropdown(
                        id="topic-dropdown",
                        options=[{"label": "All Topics", "value": ALL}],
                        value=ALL,
                        clearable=False,
                        style=_DROPDOWN_STYLE,
                    ),
                ]),
                html.Div([
                    html.Div("Country Group", style=_LABEL_STYLE),
                    dcc.Dropdown(
                        id="country-group-dropdown",
                        options=_GROUP_OPTIONS,
                        value="G7",
                        clearable=False,
                        style=_DROPDOWN_STYLE,
                    ),
                ]),
                html.Div([
                    html.Div("Index Type", style=_LABEL_STYLE),
                    dcc.Dropdown(
                        id="chart-index-type-dropdown",
                        options=_INDEX_TYPE_OPTIONS,
                        value="COMBINED",
                        clearable=False,
                        style=_DROPDOWN_STYLE,
                    ),
                ]),
            ],
            style=_FILTER_BAR,
        ),

        # ── Charts output ─────────────────────────────────────────────────────
        html.Div(id="charts-content", style={"padding": "16px 32px 24px"}),

        dcc.Interval(id="interval", interval=settings.refresh_interval_ms, n_intervals=0),
        html.Div(
            id="last-updated",
            style={"textAlign": "right", "color": "#555", "fontSize": "11px", "padding": "0 32px 12px"},
        ),
    ],
    style={"background": "#12121f", "minHeight": "100vh", "fontFamily": "Inter, sans-serif"},
)


# ── Callbacks ──────────────────────────────────────────────────────────────────

@callback(
    Output("map-topic-dropdown", "options"),
    Output("topic-dropdown", "options"),
    Input("interval", "n_intervals"),
)
def update_topic_options(n: int):
    data = fetch_json("/regional", {"hours": 168, "limit": 5000})
    if not data:
        empty = [{"label": "All Topics", "value": ALL}]
        return empty, empty
    topics = sorted({r["topic_name"] for r in data if r.get("topic_name")})
    opts = [{"label": "All Topics", "value": ALL}] + [{"label": t, "value": t} for t in topics]
    return opts, opts


@callback(
    Output("map-content", "children"),
    Output("charts-content", "children"),
    Output("last-updated", "children"),
    Input("map-topic-dropdown", "value"),
    Input("map-index-type-dropdown", "value"),
    Input("topic-dropdown", "value"),
    Input("country-group-dropdown", "value"),
    Input("chart-index-type-dropdown", "value"),
    Input("interval", "n_intervals"),
)
def update_content(
    map_topic: str, map_index_type: str,
    chart_topic: str, country_group: str, chart_index_type: str,
    n: int,
):
    ts_label = datetime.now(timezone.utc).strftime("Last updated: %Y-%m-%d %H:%M UTC")
    no_map = _empty_fig("No data — waiting for poller…", height=440)
    no_charts = html.P("No data available — waiting for poller…", style={"color": "#888"})

    data = fetch_json("/regional", {"hours": 168, "limit": 50000})
    if not data:
        return dcc.Graph(figure=no_map), no_charts, ts_label

    df = pd.DataFrame(data)
    df["publication_time"] = pd.to_datetime(df["publication_time"], utc=True)
    df = df.sort_values("publication_time")

    # ── World map: filter by map topic + map index type ───────────────────────
    map_df = df.copy()
    if map_topic != ALL:
        map_df = map_df[map_df["topic_name"] == map_topic]
    if map_index_type != ALL:
        map_df = map_df[map_df["index_type"].str.upper() == map_index_type]

    map_topic_label = "All Topics" if map_topic == ALL else map_topic
    map_index_label = "" if map_index_type == ALL else f"  ·  {map_index_type.title()}"
    latest_hour = df["publication_time"].max()
    fig_map = _build_world_map(
        map_df,
        f"Regional Macro Sentiment  ·  {map_topic_label}{map_index_label}  —  {latest_hour.strftime('%Y-%m-%d %H:%M UTC')}",
    )

    # ── Charts: filter by chart topic + country group + index type ────────────
    chart_df = df.copy()
    if chart_topic != ALL:
        chart_df = chart_df[chart_df["topic_name"] == chart_topic]
    if chart_index_type != ALL:
        chart_df = chart_df[chart_df["index_type"].str.upper() == chart_index_type]
    chart_df, active_countries = _filter_by_country_group(chart_df, country_group)

    chart_topic_label = "All Topics" if chart_topic == ALL else chart_topic
    index_suffix = "" if chart_index_type == ALL else f"  ·  {chart_index_type.title()}"
    scope_label = f"{country_group}  ·  {chart_topic_label}{index_suffix}"

    if not active_countries:
        charts = html.P("No data for the selected filters.", style={"color": "#888"})
        return dcc.Graph(figure=fig_map), charts, ts_label

    agg = _rolling_sentiment(chart_df)

    # ── Stat cards ────────────────────────────────────────────────────────────
    latest_per_country = (
        agg.sort_values("publication_time").groupby("country").last().reset_index()
    )
    mean_sentiment = latest_per_country["sentiment_smooth"].mean()
    total_headlines = int(agg["headline_count"].sum())
    positive_count = int((latest_per_country["sentiment_smooth"] > 0).sum())
    negative_count = int((latest_per_country["sentiment_smooth"] < 0).sum())

    stat_row = html.Div(
        [
            _stat_card("Mean Sentiment", f"{mean_sentiment:+.3f}", color=_sentiment_color(mean_sentiment)),
            _stat_card("Total Headlines (7d)", f"{total_headlines:,}"),
            _stat_card("Positive Countries", str(positive_count), color="#2ecc71"),
            _stat_card("Negative Countries", str(negative_count), color="#e74c3c"),
        ],
        style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "20px"},
    )

    fig_sent = _build_sentiment_ts(
        agg, active_countries,
        f"{scope_label}  —  {ROLLING_WINDOW}h Rolling Sentiment Avg  (Last 7 d)",
    )
    fig_count = _build_headline_count(
        agg, active_countries,
        f"{scope_label}  —  Hourly Headline Count  (Last 7 d)",
    )
    fig_heatmap = _build_sentiment_heatmap(
        agg, active_countries,
        f"{scope_label}  —  {ROLLING_WINDOW}h Rolling Sentiment Heatmap",
    )
    fig_topic = _build_topic(
        chart_df, f"{scope_label}  —  Mean Sentiment by Topic  (top 15 by volume)",
    )

    charts = [
        stat_row,
        dcc.Graph(figure=fig_sent,    style={"marginBottom": "16px"}),
        dcc.Graph(figure=fig_count,   style={"marginBottom": "24px"}),
        dcc.Graph(figure=fig_heatmap, style={"marginBottom": "16px"}),
        dcc.Graph(figure=fig_topic,   style={"marginBottom": "16px"}),
    ]

    return dcc.Graph(figure=fig_map), charts, ts_label


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
