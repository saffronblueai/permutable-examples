from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from config import settings
from dash import Dash, Input, Output, callback, dcc, html

# ── Colour palettes ────────────────────────────────────────────────────────────
TICKER_COLORS = px.colors.qualitative.Set2
MATCH_COLORS = {
    "EXPLICIT": "#4a90d9",
    "IMPLICIT": "#f39c12",
    "COMBINED": "#9b59b6",
}
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

ALL = "ALL"


# ── App ────────────────────────────────────────────────────────────────────────
app = Dash(__name__, title="Headline Sentiment Monitor")


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
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=14, color="#888"),
    )
    fig.update_layout(**_CHART_BASE, height=height, margin=dict(l=0, r=0, t=40, b=20))
    return fig


def _stat_card(label: str, value: str, color: str = "#ccc") -> html.Div:
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
        style=_CARD_STYLE,
    )


def _explode_countries(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["countries"] = out["countries"].fillna("").str.split("|")
    out = out.explode("countries")
    out["countries"] = out["countries"].str.strip()
    return out[out["countries"] != ""]


def _match_color(mt: str) -> str:
    return MATCH_COLORS.get(str(mt).upper(), "#aaa")


# ── Chart builders ─────────────────────────────────────────────────────────────


def _build_sentiment(df: pd.DataFrame, active_tickers: list[str], title: str) -> go.Figure:
    fig = go.Figure()
    for i, ticker in enumerate(active_tickers):
        color = TICKER_COLORS[i % len(TICKER_COLORS)]
        sub = df[df["ticker"] == ticker].set_index("publication_time")["sentiment_score"].dropna()
        if sub.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=sub.index,
                y=sub.values,
                mode="markers",
                marker=dict(size=4, color=color, opacity=0.2),
                name=f"{ticker} raw",
                legendgroup=ticker,
            )
        )
        rolling = sub.resample("30min").mean().rolling(3, min_periods=1).mean()
        fig.add_trace(
            go.Scatter(
                x=rolling.index,
                y=rolling.values,
                mode="lines",
                line=dict(color=color, width=2),
                name=f"{ticker} 30-min",
                legendgroup=ticker,
            )
        )
    fig.add_hline(y=0, line_dash="dot", line_color="#555", line_width=1)
    fig.update_layout(
        **_CHART_BASE,
        title=title,
        xaxis_title="Time (UTC)",
        yaxis_title="Sentiment Score",
        yaxis=dict(range=[-1.05, 1.05]),
        legend=_LEGEND,
        height=360,
        margin=dict(l=0, r=160, t=60, b=40),
    )
    return fig


def _build_count_time(df: pd.DataFrame, active_tickers: list[str], title: str) -> go.Figure:
    df2 = df.copy()
    df2["hour"] = df2["publication_time"].dt.floor("1h")
    count_df = df2.groupby(["hour", "ticker"]).size().reset_index(name="n")
    fig = go.Figure()
    for i, ticker in enumerate(active_tickers):
        color = TICKER_COLORS[i % len(TICKER_COLORS)]
        sub = count_df[count_df["ticker"] == ticker]
        fig.add_trace(go.Bar(x=sub["hour"], y=sub["n"], name=ticker, marker_color=color))
    fig.update_layout(
        **_CHART_BASE,
        barmode="stack",
        title=title,
        xaxis_title="Time (UTC)",
        yaxis_title="Headline Count",
        legend=_LEGEND,
        height=260,
        margin=dict(l=0, r=160, t=60, b=40),
    )
    return fig


def _build_map(df: pd.DataFrame, title: str) -> go.Figure:
    """Choropleth world map — mean sentiment per country (stored as country names)."""
    cdf = _explode_countries(df)
    if cdf.empty:
        return _empty_fig("No country data available", height=450)

    country_sent = cdf.groupby("countries")["sentiment_score"].agg(sentiment="mean", count="size").reset_index()
    if country_sent.empty:
        return _empty_fig("No country sentiment data", height=450)

    abs_max = country_sent["sentiment"].abs().max()
    abs_max = max(abs_max, 0.05)  # prevent degenerate scale

    fig = go.Figure(
        go.Choropleth(
            locations=country_sent["countries"],
            z=country_sent["sentiment"],
            locationmode="country names",
            colorscale=[
                [0.0, "#c0392b"],
                [0.35, "#7f1010"],
                [0.5, "#2a2a3e"],
                [0.65, "#0e4d1a"],
                [1.0, "#2ecc71"],
            ],
            zmid=0,
            zmin=-abs_max,
            zmax=abs_max,
            colorbar=dict(
                title=dict(text="Sentiment", font=dict(color="#ccc")),
                tickfont=dict(color="#ccc"),
                x=1.0,
                xanchor="left",
                thickness=14,
                len=0.75,
            ),
            text=country_sent["countries"],
            customdata=country_sent[["sentiment", "count"]],
            hovertemplate=(
                "<b>%{text}</b><br>" "Sentiment: %{customdata[0]:.3f}<br>" "Headlines: %{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **_CHART_BASE,
        title=title,
        geo=dict(
            showframe=False,
            showcoastlines=True,
            coastlinecolor="#444",
            showland=True,
            landcolor="#2a2a3e",
            showocean=True,
            oceancolor="#1a1a2e",
            showlakes=False,
            showcountries=True,
            countrycolor="#333",
            bgcolor="#1a1a2e",
            projection_type="natural earth",
        ),
        height=460,
        margin=dict(l=0, r=0, t=60, b=0),
    )
    return fig


def _build_topic(df: pd.DataFrame, title: str, top_n: int = 15) -> go.Figure:
    top_topics = df.groupby("topic_name")["sentiment_score"].count().nlargest(top_n).index
    topic_df = (
        df[df["topic_name"].isin(top_topics)]
        .groupby("topic_name")["sentiment_score"]
        .mean()
        .sort_values()
        .reset_index()
    )
    if topic_df.empty:
        return _empty_fig(height=340)
    fig = go.Figure(
        go.Bar(
            x=topic_df["sentiment_score"],
            y=topic_df["topic_name"],
            orientation="h",
            marker_color=["#e74c3c" if v < 0 else "#2ecc71" for v in topic_df["sentiment_score"]],
        )
    )
    fig.add_vline(x=0, line_color="#555", line_dash="dash", line_width=1)
    fig.update_layout(
        **_CHART_BASE,
        title=title,
        xaxis_title="Mean Sentiment Score",
        height=max(340, len(topic_df) * 28 + 80),
        margin=dict(l=0, r=0, t=50, b=30),
    )
    return fig


def _build_language(df: pd.DataFrame, match_types: list[str], top_n: int = 12) -> go.Figure:
    lang_df = df[df["language"].notna() & (df["language"] != "")]
    top_langs = lang_df["language"].value_counts().nlargest(top_n).index.tolist()
    counts = (
        lang_df[lang_df["language"].isin(top_langs)].groupby(["language", "match_type"]).size().reset_index(name="n")
    )
    fig = go.Figure()
    for mt in match_types:
        sub = counts[counts["match_type"] == mt].set_index("language")["n"]
        fig.add_trace(
            go.Bar(
                x=top_langs,
                y=[sub.get(l, 0) for l in top_langs],
                name=mt,
                marker_color=_match_color(mt),
            )
        )
    fig.update_layout(
        **_CHART_BASE,
        barmode="group",
        title=f"Headlines by Language  (top {top_n})  —  by match type",
        xaxis_title="Language",
        yaxis_title="Headline Count",
        legend=_LEGEND,
        height=300,
        margin=dict(l=0, r=160, t=60, b=40),
    )
    return fig


def _build_country(df: pd.DataFrame, match_types: list[str], top_n: int = 15) -> go.Figure:
    cdf = _explode_countries(df)
    if cdf.empty:
        return _empty_fig(height=320)
    top_countries = cdf["countries"].value_counts().nlargest(top_n).index
    cdf = cdf[cdf["countries"].isin(top_countries)]
    sent_by = cdf.groupby(["countries", "match_type"])["sentiment_score"].mean().reset_index(name="sent")
    country_order = cdf.groupby("countries")["sentiment_score"].mean().sort_values().index.tolist()
    fig = go.Figure()
    for mt in match_types:
        sub = sent_by[sent_by["match_type"] == mt].set_index("countries")["sent"]
        fig.add_trace(
            go.Bar(
                x=[sub.get(c, None) for c in country_order],
                y=country_order,
                orientation="h",
                name=mt,
                marker_color=_match_color(mt),
            )
        )
    fig.add_vline(x=0, line_color="#555", line_dash="dash", line_width=1)
    fig.update_layout(
        **_CHART_BASE,
        barmode="group",
        title=f"Mean Sentiment by Country  (top {top_n} by volume)  —  by match type",
        xaxis_title="Mean Sentiment Score",
        legend=_LEGEND,
        height=max(300, len(country_order) * 22 + 100),
        margin=dict(l=0, r=160, t=60, b=30),
    )
    return fig


# ── Layout ─────────────────────────────────────────────────────────────────────

_ticker_options = [{"label": "All tickers", "value": ALL}] + [{"label": t, "value": t} for t in settings.tickers_list]

app.layout = html.Div(
    [
        html.Div(
            [
                html.Div(
                    [
                        html.H1(
                            "Headline Sentiment Monitor", style={"margin": "0", "color": "#fff", "fontSize": "20px"}
                        ),
                        html.P(
                            "Permutable AI  ·  Live Polling Application",
                            style={"margin": "2px 0 0", "color": "#aaa", "fontSize": "12px"},
                        ),
                    ]
                ),
                dcc.Dropdown(
                    id="ticker-dropdown",
                    options=_ticker_options,
                    value=ALL,
                    clearable=False,
                    style={"minWidth": "200px", "color": "#000", "fontSize": "13px"},
                ),
            ],
            style={
                "background": "#0f0f1a",
                "padding": "16px 32px",
                "borderBottom": "2px solid #222",
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "space-between",
                "gap": "24px",
            },
        ),
        html.Div(id="main-content", style={"padding": "24px 32px"}),
        dcc.Interval(id="interval", interval=settings.refresh_interval_ms, n_intervals=0),
        html.Div(
            id="last-updated",
            style={"textAlign": "right", "color": "#555", "fontSize": "11px", "padding": "0 32px 12px"},
        ),
    ],
    style={"background": "#12121f", "minHeight": "100vh", "fontFamily": "Inter, sans-serif"},
)


# ── Main callback ──────────────────────────────────────────────────────────────


@callback(
    Output("main-content", "children"),
    Output("last-updated", "children"),
    Input("ticker-dropdown", "value"),
    Input("interval", "n_intervals"),
)
def update_content(selected: str, n: int):
    ts_label = datetime.now(timezone.utc).strftime("Last updated: %Y-%m-%d %H:%M UTC")

    ticker_param = None if selected == ALL else selected
    data = fetch_json(
        "/headlines",
        {
            "hours": 24,
            "limit": 10000,
            **({"ticker": ticker_param} if ticker_param else {}),
        },
    )
    if not data:
        return [html.P("No data available — waiting for poller…", style={"color": "#888"})], ts_label

    df = pd.DataFrame(data)
    df["publication_time"] = pd.to_datetime(df["publication_time"], utc=True)
    df = df.sort_values("publication_time")
    df["match_type"] = df["match_type"].fillna("UNKNOWN").str.upper()
    match_types = sorted(df["match_type"].unique())

    if selected == ALL:
        active_tickers = [t for t in settings.tickers_list if t in df["ticker"].unique()]
        scope_label = "All Tickers"
    else:
        active_tickers = [selected]
        scope_label = selected

    # ── Stat cards ─────────────────────────────────────────────────────────────
    mean_sent = df["sentiment_score"].mean()
    avg_bull = df["bullish_probability"].mean() * 100 if "bullish_probability" in df else 0
    avg_bear = df["bearish_probability"].mean() * 100 if "bearish_probability" in df else 0
    sent_color = "#2ecc71" if mean_sent > 0.02 else ("#e74c3c" if mean_sent < -0.02 else "#95a5a6")

    stat_row = html.Div(
        [
            _stat_card("Headlines (24 h)", str(len(df))),
            _stat_card("Mean Sentiment", f"{mean_sent:+.3f}", color=sent_color),
            _stat_card("Avg Bullish %", f"{avg_bull:.1f}%", color="#2ecc71"),
            _stat_card("Avg Bearish %", f"{avg_bear:.1f}%", color="#e74c3c"),
        ],
        style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "20px"},
    )

    fig_sent = _build_sentiment(df, active_tickers, f"{scope_label}  —  30-Min Smoothed Sentiment  (Last 24 h)")
    fig_count = _build_count_time(df, active_tickers, f"{scope_label}  —  Headline Count per Hour  (Last 24 h)")
    fig_map = _build_map(df, f"{scope_label}  —  Mean Sentiment by Country")
    fig_topic = _build_topic(df, f"{scope_label}  —  Mean Sentiment by Topic  (top 15 by volume)")
    fig_lang = _build_language(df, match_types)
    fig_ctry = _build_country(df, match_types)

    _cell = {"flex": "1 1 45%", "minWidth": "340px"}

    return [
        stat_row,
        dcc.Graph(figure=fig_sent,  style={"marginBottom": "16px"}),
        dcc.Graph(figure=fig_count, style={"marginBottom": "24px"}),

        # 2 × 2 grid: map | topic  /  language | country
        html.Div(
            [
                dcc.Graph(figure=fig_map,   style=_cell),
                dcc.Graph(figure=fig_topic, style=_cell),
                dcc.Graph(figure=fig_lang,  style=_cell),
                dcc.Graph(figure=fig_ctry,  style=_cell),
            ],
            style={"display": "flex", "flexWrap": "wrap", "gap": "16px"},
        ),
    ], ts_label


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
