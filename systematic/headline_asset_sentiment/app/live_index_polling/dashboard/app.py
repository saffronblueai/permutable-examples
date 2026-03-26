from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from config import settings
from dash import Dash, Input, Output, callback, dcc, html

# ── Colour palettes ────────────────────────────────────────────────────────────
TICKER_COLORS = px.colors.qualitative.Set2
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
ROLLING_WINDOW = 5  # hours for sentiment rolling mean


# ── App ────────────────────────────────────────────────────────────────────────
app = Dash(__name__, title="Headline Index Monitor")


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


def _sentiment_color(v: float) -> str:
    if v >= settings.upper_threshold:
        return "#2ecc71"
    if v <= settings.lower_threshold:
        return "#e74c3c"
    return "#95a5a6"


def _rolling_sentiment_avg(df: pd.DataFrame, active_tickers: list[str]) -> pd.DataFrame:
    """Aggregate to (ticker, hour), compute average sentiment and rolling mean."""
    agg = (
        df.groupby(["ticker", "publication_time"])
        .agg(
            sentiment_sum=("sentiment_sum", "sum"),
            headline_count=("headline_count", "sum"),
        )
        .reset_index()
        .sort_values(["ticker", "publication_time"])
    )
    agg["sentiment_avg"] = agg["sentiment_sum"] / agg["headline_count"].replace(0, float("nan"))
    agg["sentiment_avg"] = agg["sentiment_avg"].fillna(0.0)
    agg["sentiment_smooth"] = agg.groupby("ticker")["sentiment_avg"].transform(
        lambda x: x.rolling(ROLLING_WINDOW, min_periods=1).mean()
    )
    return agg


# ── Chart builders ─────────────────────────────────────────────────────────────


def _build_sentiment_ts(agg: pd.DataFrame, active_tickers: list[str], title: str) -> go.Figure:
    fig = go.Figure()
    for i, ticker in enumerate(active_tickers):
        color = TICKER_COLORS[i % len(TICKER_COLORS)]
        sub = agg[agg["ticker"] == ticker].sort_values("publication_time")
        if sub.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=sub["publication_time"],
                y=sub["sentiment_avg"],
                mode="lines",
                line=dict(color=color, width=1, dash="dot"),
                name=f"{ticker} raw",
                legendgroup=ticker,
                opacity=0.4,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=sub["publication_time"],
                y=sub["sentiment_smooth"],
                mode="lines",
                line=dict(color=color, width=2),
                name=f"{ticker} {ROLLING_WINDOW}h rolling",
                legendgroup=ticker,
            )
        )
    fig.add_hline(
        y=settings.upper_threshold,
        line_dash="dash",
        line_color="#2ecc71",
        line_width=1,
        annotation_text="HIGH",
        annotation_position="right",
    )
    fig.add_hline(
        y=settings.lower_threshold,
        line_dash="dash",
        line_color="#e74c3c",
        line_width=1,
        annotation_text="LOW",
        annotation_position="right",
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#555", line_width=1)
    fig.update_layout(
        **_CHART_BASE,
        title=title,
        xaxis_title="Time (UTC)",
        yaxis_title="Avg Sentiment  [−1, +1]",
        yaxis=dict(range=[-1.05, 1.05]),
        legend=_LEGEND,
        height=380,
        margin=dict(l=0, r=160, t=60, b=40),
    )
    return fig


def _build_headline_count(agg: pd.DataFrame, active_tickers: list[str], title: str) -> go.Figure:
    fig = go.Figure()
    for i, ticker in enumerate(active_tickers):
        color = TICKER_COLORS[i % len(TICKER_COLORS)]
        sub = agg[agg["ticker"] == ticker].sort_values("publication_time")
        fig.add_trace(
            go.Bar(
                x=sub["publication_time"],
                y=sub["headline_count"],
                name=ticker,
                marker_color=color,
            )
        )
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


def _build_sentiment_heatmap(agg: pd.DataFrame, active_tickers: list[str], title: str) -> go.Figure:
    """5-period rolling average sentiment heatmap — ticker × hour, date ticks at day boundaries."""
    pivot = (
        agg.pivot_table(index="publication_time", columns="ticker", values="sentiment_smooth", aggfunc="mean")
        .reindex(columns=active_tickers)
        .sort_index()
    )
    if pivot.empty:
        return _empty_fig("Not enough data for heatmap", height=200)

    # Plotly heatmap with RdYlGn colorscale
    z = pivot.values.T  # shape: (tickers, hours)
    x_labels = pivot.index.strftime("%b %d %H:%M").tolist()

    # Compute day-boundary positions for sparse x-axis ticks
    seen_dates: set = set()
    tick_positions: list[int] = []
    tick_labels: list[str] = []
    for i, t in enumerate(pivot.index):
        d = t.date()
        if d not in seen_dates:
            seen_dates.add(d)
            tick_positions.append(i)
            tick_labels.append(t.strftime("%b %d"))

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=x_labels,
            y=active_tickers,
            colorscale=[
                [0.0, "#c0392b"],
                [0.5, "#f39c12"],
                [1.0, "#2ecc71"],
            ],
            zmid=0,
            zmin=-1,
            zmax=1,
            colorbar=dict(
                title=dict(text="Avg Sentiment", font=dict(color="#ccc")),
                tickfont=dict(color="#ccc"),
                x=1.0,
                xanchor="left",
                thickness=14,
                len=0.75,
            ),
            hovertemplate="<b>%{y}</b> — %{x}<br>Avg Sentiment: %{z:.3f}<extra></extra>",
        )
    )
    fig.update_layout(
        **_CHART_BASE,
        title=title,
        xaxis=dict(
            tickmode="array",
            tickvals=[x_labels[i] for i in tick_positions],
            ticktext=tick_labels,
            tickangle=30,
        ),
        yaxis_title="Ticker",
        height=max(200, len(active_tickers) * 50 + 100),
        margin=dict(l=0, r=80, t=60, b=60),
    )
    return fig


def _build_indicator_heatmap(agg: pd.DataFrame, active_tickers: list[str], title: str) -> go.Figure:
    """Colour-coded HIGH / NEUTRAL / LOW heatmap — ticker × hour, date ticks."""
    pivot = (
        agg.pivot_table(index="publication_time", columns="ticker", values="sentiment_smooth", aggfunc="mean")
        .reindex(columns=active_tickers)
        .sort_index()
    )
    if pivot.empty:
        return _empty_fig("Not enough data for indicator heatmap", height=200)

    # Map to ternary numeric: HIGH=1, NEUTRAL=0, LOW=-1
    num = pivot.copy()
    num[pivot >= settings.upper_threshold] = 1
    num[(pivot > settings.lower_threshold) & (pivot < settings.upper_threshold)] = 0
    num[pivot <= settings.lower_threshold] = -1

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

    fig = go.Figure(
        go.Heatmap(
            z=num.values.T,
            x=x_labels,
            y=active_tickers,
            colorscale=[[0.0, "#e74c3c"], [0.5, "#bdc3c7"], [1.0, "#2ecc71"]],
            zmid=0,
            zmin=-1,
            zmax=1,
            showscale=False,
            hovertemplate="<b>%{y}</b> — %{x}<br>Indicator: %{z}<extra></extra>",
        )
    )
    # Add invisible traces for legend
    for label, color, val in [
        (f"HIGH (≥{settings.upper_threshold})", "#2ecc71", 1),
        ("NEUTRAL", "#bdc3c7", 0),
        (f"LOW (≤{settings.lower_threshold})", "#e74c3c", -1),
    ]:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker=dict(size=10, color=color, symbol="square"),
                name=label,
                showlegend=True,
            )
        )
    fig.update_layout(
        **_CHART_BASE,
        title=title,
        xaxis=dict(
            tickmode="array",
            tickvals=[x_labels[i] for i in tick_positions],
            ticktext=tick_labels,
            tickangle=30,
        ),
        legend=_LEGEND,
        height=max(200, len(active_tickers) * 50 + 120),
        margin=dict(l=0, r=160, t=60, b=60),
    )
    return fig


def _build_topic(df: pd.DataFrame, title: str, top_n: int = 15) -> go.Figure:
    """Mean average sentiment by topic (top N by total headline volume)."""
    agg = (
        df.groupby(["ticker", "publication_time", "topic_name"])
        .agg(
            sentiment_sum=("sentiment_sum", "sum"),
            headline_count=("headline_count", "sum"),
        )
        .reset_index()
    )
    agg["sentiment_avg"] = agg["sentiment_sum"] / agg["headline_count"].replace(0, float("nan"))

    top_topics = df.groupby("topic_name")["headline_count"].sum().nlargest(top_n).index
    topic_df = (
        agg[agg["topic_name"].isin(top_topics)]
        .groupby("topic_name")["sentiment_avg"]
        .mean()
        .sort_values()
        .reset_index()
    )
    if topic_df.empty:
        return _empty_fig(height=340)
    fig = go.Figure(
        go.Bar(
            x=topic_df["sentiment_avg"],
            y=topic_df["topic_name"],
            orientation="h",
            marker_color=["#e74c3c" if v < 0 else "#2ecc71" for v in topic_df["sentiment_avg"]],
        )
    )
    fig.add_vline(x=0, line_color="#555", line_dash="dash", line_width=1)
    fig.update_layout(
        **_CHART_BASE,
        title=title,
        xaxis_title="Mean Avg Sentiment",
        xaxis=dict(range=[-1.05, 1.05]),
        height=max(340, len(topic_df) * 28 + 80),
        margin=dict(l=0, r=0, t=50, b=30),
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
                        html.H1("Headline Index Monitor", style={"margin": "0", "color": "#fff", "fontSize": "20px"}),
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
        "/index",
        {
            "hours": 168,  # 7 days to match default backfill
            "limit": 50000,
            **({"ticker": ticker_param} if ticker_param else {}),
        },
    )
    if not data:
        return [html.P("No data available — waiting for poller…", style={"color": "#888"})], ts_label

    df = pd.DataFrame(data)
    df["publication_time"] = pd.to_datetime(df["publication_time"], utc=True)
    df = df.sort_values("publication_time")

    if selected == ALL:
        active_tickers = [t for t in settings.tickers_list if t in df["ticker"].unique()]
        scope_label = "All Tickers"
    else:
        active_tickers = [selected]
        scope_label = selected

    agg = _rolling_sentiment_avg(df, active_tickers)

    # ── Stat cards ──────────────────────────────────────────────────────────
    latest_per_ticker = agg.sort_values("publication_time").groupby("ticker").last().reset_index()
    mean_sentiment = latest_per_ticker["sentiment_smooth"].mean()
    total_headlines = int(agg["headline_count"].sum())
    high_count = int((latest_per_ticker["sentiment_smooth"] >= settings.upper_threshold).sum())
    low_count = int((latest_per_ticker["sentiment_smooth"] <= settings.lower_threshold).sum())

    sent_color = _sentiment_color(mean_sentiment)

    stat_row = html.Div(
        [
            _stat_card("Index records (7d)", f"{len(df):,}"),
            _stat_card("Mean avg sentiment", f"{mean_sentiment:+.3f}", color=sent_color),
            _stat_card("Total headlines (7d)", f"{total_headlines:,}"),
            _stat_card("HIGH tickers", str(high_count), color="#2ecc71"),
            _stat_card("LOW tickers", str(low_count), color="#e74c3c"),
        ],
        style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "20px"},
    )

    fig_sent = _build_sentiment_ts(
        agg,
        active_tickers,
        f"{scope_label}  —  {ROLLING_WINDOW}h Rolling Avg Sentiment  (Last 7 d)",
    )
    fig_count = _build_headline_count(
        agg,
        active_tickers,
        f"{scope_label}  —  Hourly Headline Count  (Last 7 d)",
    )
    fig_heatmap = _build_sentiment_heatmap(
        agg,
        active_tickers,
        f"{scope_label}  —  {ROLLING_WINDOW}h Rolling Avg Sentiment Heatmap",
    )
    fig_indicator = _build_indicator_heatmap(
        agg,
        active_tickers,
        f"{scope_label}  —  Sentiment Indicator  "
        f"(HIGH ≥ {settings.upper_threshold} | LOW ≤ {settings.lower_threshold})",
    )
    fig_topic = _build_topic(
        df,
        f"{scope_label}  —  Mean Avg Sentiment by Topic  (top 15 by volume)",
    )

    _cell = {"flex": "1 1 45%", "minWidth": "340px"}

    return [
        stat_row,
        dcc.Graph(figure=fig_sent, style={"marginBottom": "16px"}),
        dcc.Graph(figure=fig_count, style={"marginBottom": "24px"}),
        dcc.Graph(figure=fig_heatmap, style={"marginBottom": "16px"}),
        dcc.Graph(figure=fig_indicator, style={"marginBottom": "24px"}),
        dcc.Graph(figure=fig_topic, style={"marginBottom": "16px"}),
    ], ts_label


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
