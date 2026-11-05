from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from config import settings
from dash import Dash, Input, Output, callback, dcc, html

# ── Colour palettes ────────────────────────────────────────────────────────────
TICKER_COLORS = px.colors.qualitative.Set2
HORIZON_COLORS = {"short_term": "#3498db", "medium_term": "#f39c12", "long_term": "#2ecc71"}
INDICATOR_COLORS = {"HIGH": "#2ecc71", "NEUTRAL": "#bdc3c7", "LOW": "#e74c3c", "NO_READING": "#2e2e45"}
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
HORIZONS = ["short_term", "medium_term", "long_term"]

app = Dash(__name__, title="GCSI Index Monitor")


# ── Helpers ────────────────────────────────────────────────────────────────────


def fetch_json(path: str, params: dict | None = None) -> list | dict | None:
    try:
        r = requests.get(f"{settings.api_url}{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fetch_frame(path: str, params: dict) -> pd.DataFrame:
    df = pd.DataFrame(fetch_json(path, params) or [])
    if not df.empty and "extraction_time" in df:
        df["extraction_time"] = pd.to_datetime(df["extraction_time"], utc=True)
    return df


def _empty_fig(message: str = "No data: waiting for poller…", height: int = 300) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                       font=dict(size=14, color="#888"))
    fig.update_layout(**_CHART_BASE, height=height, margin=dict(l=0, r=0, t=40, b=20))
    return fig


def _stat_card(label: str, value: str, color: str = "#ccc") -> html.Div:
    return html.Div(
        [
            html.Div(label, style={"color": "#888", "fontSize": "11px", "marginBottom": "6px",
                                   "textTransform": "uppercase", "letterSpacing": "0.05em"}),
            html.Div(value, style={"color": color, "fontSize": "22px", "fontWeight": "700"}),
        ],
        style=_CARD_STYLE,
    )


# ── Chart builders ─────────────────────────────────────────────────────────────


def _build_sentiment_ts(series: pd.DataFrame, tickers: list[str], title: str) -> go.Figure:
    if series.empty:
        return _empty_fig(height=380)
    fig = go.Figure()
    for i, ticker in enumerate(tickers):
        sub = series[series["ticker"] == ticker]
        if sub.empty:
            continue
        color = TICKER_COLORS[i % len(TICKER_COLORS)]
        fig.add_trace(go.Scatter(x=sub["extraction_time"], y=sub["sentiment_smooth"], mode="lines",
                                 line=dict(color=color, width=2), name=ticker))
        if len(tickers) == 1 and sub["upper"].notna().any():
            # Thresholds are calibrated per ticker, so they are drawn only for a single ticker.
            for level, label, colour in [("upper", "HIGH", "#2ecc71"), ("lower", "LOW", "#e74c3c")]:
                fig.add_hline(y=float(sub[level].iloc[-1]), line_dash="dash", line_color=colour, line_width=1,
                              annotation_text=label, annotation_position="right")
    fig.add_hline(y=0, line_dash="dot", line_color="#555", line_width=1)
    fig.update_layout(**_CHART_BASE, title=title, xaxis_title="Time (UTC)",
                      yaxis_title="Weighted avg sentiment", legend=_LEGEND, height=380,
                      margin=dict(l=0, r=160, t=60, b=40))
    return fig


def _build_volume(series: pd.DataFrame, tickers: list[str], title: str) -> go.Figure:
    if series.empty:
        return _empty_fig(height=260)
    fig = go.Figure()
    for i, ticker in enumerate(tickers):
        sub = series[series["ticker"] == ticker]
        fig.add_trace(go.Bar(x=sub["extraction_time"], y=sub["headline_count"], name=ticker,
                             marker_color=TICKER_COLORS[i % len(TICKER_COLORS)]))
    fig.update_layout(**_CHART_BASE, barmode="stack", title=title, xaxis_title="Time (UTC)",
                      yaxis_title="Topic-links", legend=_LEGEND, height=260, margin=dict(l=0, r=160, t=60, b=40))
    return fig


def _build_indicator_heatmap(series: pd.DataFrame, tickers: list[str], title: str) -> go.Figure:
    if series.empty:
        return _empty_fig("Not enough data for the indicator heatmap", height=200)
    codes = {"LOW": -1, "NEUTRAL": 0, "HIGH": 1}
    pivot = (
        series.assign(code=series["indicator"].map(codes))
        .pivot_table(index="ticker", columns="extraction_time", values="code", aggfunc="last")
        .reindex([t for t in tickers if t in set(series["ticker"])])
    )
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns, y=pivot.index, zmin=-1, zmax=1, showscale=False,
        colorscale=[[0.0, INDICATOR_COLORS["LOW"]], [0.5, INDICATOR_COLORS["NEUTRAL"]], [1.0, INDICATOR_COLORS["HIGH"]]],
        hovertemplate="<b>%{y}</b> %{x}<br>Indicator: %{z}<extra></extra>",
    ))
    for label in ["HIGH", "NEUTRAL", "LOW"]:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=label,
                                 marker=dict(size=10, color=INDICATOR_COLORS[label], symbol="square")))
    fig.update_layout(**_CHART_BASE, title=title, legend=_LEGEND, height=max(200, len(pivot) * 50 + 120),
                      margin=dict(l=0, r=160, t=60, b=40))
    return fig


def _build_horizons(frames: dict[str, pd.DataFrame], ticker: str, title: str) -> go.Figure:
    fig = go.Figure()
    for horizon, frame in frames.items():
        sub = frame[frame["ticker"] == ticker] if not frame.empty else frame
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(x=sub["extraction_time"], y=sub["sentiment_smooth"], mode="lines",
                                 line=dict(color=HORIZON_COLORS[horizon], width=2), name=horizon))
    if not fig.data:
        return _empty_fig(height=320)
    fig.add_hline(y=0, line_dash="dot", line_color="#555", line_width=1)
    fig.update_layout(**_CHART_BASE, title=title, xaxis_title="Time (UTC)", yaxis_title="Weighted avg sentiment",
                      legend=_LEGEND, height=320, margin=dict(l=0, r=160, t=60, b=40))
    return fig


def _build_topics(topics: pd.DataFrame, title: str) -> go.Figure:
    if topics.empty:
        return _empty_fig(height=340)
    topics = topics.sort_values("sentiment_avg")
    fig = go.Figure(go.Bar(
        x=topics["sentiment_avg"], y=topics["topic_name"], orientation="h",
        marker_color=["#e74c3c" if v < 0 else "#2ecc71" for v in topics["sentiment_avg"]],
        customdata=topics["headline_count"],
        hovertemplate="%{y}<br>Avg: %{x:.3f}<br>Topic-links: %{customdata}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#555", line_dash="dash", line_width=1)
    fig.update_layout(**_CHART_BASE, title=title, xaxis_title="Volume-weighted average sentiment",
                      height=max(340, len(topics) * 28 + 80), margin=dict(l=0, r=0, t=50, b=30))
    return fig


# ── Layout ─────────────────────────────────────────────────────────────────────

_dropdown_style = {"minWidth": "180px", "color": "#000", "fontSize": "13px"}
app.layout = html.Div(
    [
        html.Div(
            [
                html.Div([
                    html.H1("GCSI Index Monitor", style={"margin": "0", "color": "#fff", "fontSize": "20px"}),
                    html.P("Permutable AI  ·  Global Commodity Sentiment Indices  ·  Live Polling Application",
                           style={"margin": "2px 0 0", "color": "#aaa", "fontSize": "12px"}),
                ]),
                html.Div(
                    [
                        dcc.Dropdown(id="ticker-dropdown", value=ALL, clearable=False, style=_dropdown_style,
                                     options=[{"label": "All tickers", "value": ALL}]
                                     + [{"label": t, "value": t} for t in settings.tickers_list]),
                        dcc.Dropdown(id="horizon-dropdown", value="short_term", clearable=False, style=_dropdown_style,
                                     options=[{"label": h, "value": h} for h in HORIZONS]),
                        dcc.Dropdown(id="index-type-dropdown", value=settings.index_types_list[0], clearable=False,
                                     style=_dropdown_style,
                                     options=[{"label": t, "value": t} for t in settings.index_types_list]),
                    ],
                    style={"display": "flex", "gap": "12px"},
                ),
            ],
            style={"background": "#0f0f1a", "padding": "16px 32px", "borderBottom": "2px solid #222",
                   "display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "24px"},
        ),
        html.Div(id="main-content", style={"padding": "24px 32px"}),
        dcc.Interval(id="interval", interval=settings.refresh_interval_ms, n_intervals=0),
        html.Div(id="last-updated", style={"textAlign": "right", "color": "#555", "fontSize": "11px",
                                           "padding": "0 32px 12px"}),
    ],
    style={"background": "#12121f", "minHeight": "100vh", "fontFamily": "Inter, sans-serif"},
)


# ── Main callback ──────────────────────────────────────────────────────────────


@callback(
    Output("main-content", "children"),
    Output("last-updated", "children"),
    Input("ticker-dropdown", "value"),
    Input("horizon-dropdown", "value"),
    Input("index-type-dropdown", "value"),
    Input("interval", "n_intervals"),
)
def update_content(selected: str, horizon: str, index_type: str, n: int):
    ts_label = datetime.now(timezone.utc).strftime("Last updated: %Y-%m-%d %H:%M UTC")
    ticker = None if selected == ALL else selected
    hours = settings.dashboard_hours
    common = {"index_type": index_type, "hours": hours, **({"ticker": ticker} if ticker else {})}

    series = fetch_frame("/sentiment/history", {**common, "sentiment_type": horizon})
    if series.empty:
        return [html.P("No data available: waiting for poller…", style={"color": "#888"})], ts_label

    tickers = [t for t in settings.tickers_list if t in set(series["ticker"])] if ticker is None else [ticker]
    scope = "All tickers" if ticker is None else ticker
    latest = series.sort_values("extraction_time").groupby("ticker").tail(1)
    newest = series["extraction_time"].max()
    last_day = series[series["extraction_time"] > newest - pd.Timedelta(hours=24)]

    stat_row = html.Div(
        [
            _stat_card("Newest bar (UTC)", f"{newest:%d %b %H:%M}"),
            _stat_card("Topic-links (24h)", f"{int(last_day['headline_count'].sum()):,}"),
            _stat_card("HIGH tickers", str(int((latest["indicator"] == "HIGH").sum())), color="#2ecc71"),
            _stat_card("LOW tickers", str(int((latest["indicator"] == "LOW").sum())), color="#e74c3c"),
        ],
        style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "20px"},
    )

    label = f"{scope}  |  {horizon}  |  {index_type}"
    content = [
        stat_row,
        dcc.Graph(figure=_build_sentiment_ts(series, tickers, f"{label}  |  24h weighted average sentiment"),
                  style={"marginBottom": "16px"}),
        dcc.Graph(figure=_build_volume(series, tickers, f"{label}  |  hourly topic-links"),
                  style={"marginBottom": "24px"}),
        dcc.Graph(figure=_build_indicator_heatmap(series, tickers, f"{label}  |  indicator (thresholds calibrated per ticker)"),
                  style={"marginBottom": "24px"}),
    ]
    if ticker is not None:
        frames = {h: fetch_frame("/sentiment/history", {**common, "sentiment_type": h}) for h in HORIZONS}
        content.append(dcc.Graph(figure=_build_horizons(frames, ticker, f"{ticker}  |  {index_type}  |  horizons compared"),
                                 style={"marginBottom": "24px"}))
    topics = pd.DataFrame(fetch_json("/topics", {**common, "sentiment_type": horizon, "limit": 15}) or [])
    content.append(dcc.Graph(figure=_build_topics(topics, f"{label}  |  15 busiest topics, volume-weighted")))
    return content, ts_label


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
