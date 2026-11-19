from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
from config import settings, ticker_label
from dash import Dash, Input, Output, callback, dcc, html

# ── Theme ──────────────────────────────────────────────────────────────────────
PAGE = "#0d0d0d"
SURFACE = "#1a1a19"
INK = "#f0efec"
INK_2 = "#c3c2b7"
MUTED = "#898781"
GRID = "#2c2c2a"
BASELINE = "#383835"
BORDER = "1px solid rgba(255, 255, 255, 0.10)"
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

# Categorical slots in a fixed order (checked for colour-blind separation on the dark surface).
# A ticker keeps its slot whatever the filter shows.
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
HORIZON_COLORS = {"short_term": SERIES[0], "medium_term": SERIES[1], "long_term": SERIES[2]}
INDICATOR_COLORS = {"HIGH": "#0ca30c", "NEUTRAL": BASELINE, "LOW": "#d03b3b"}
POSITIVE, NEGATIVE = "#0ca30c", "#d03b3b"

ALL = "ALL"
HORIZONS = ["short_term", "medium_term", "long_term"]
HORIZON_LABELS = {"short_term": "Short term", "medium_term": "Medium term", "long_term": "Long term"}

_CARD_STYLE = {"background": SURFACE, "border": BORDER, "borderRadius": "10px"}
_GRAPH_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}

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
    if not df.empty and "processed_at" in df:
        df["processed_at"] = pd.to_datetime(df["processed_at"], utc=True)
    return df


def ticker_color(ticker: str) -> str:
    """Colour by the ticker's position in TICKERS, so a filter never repaints a series."""
    tickers = settings.tickers_list
    slot = tickers.index(ticker) if ticker in tickers else len(tickers)
    return SERIES[slot] if slot < len(SERIES) else MUTED


def _style(fig: go.Figure, title: str, height: int, legend: bool = True) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT, size=12, color=INK_2),
        title=dict(text=title, x=0.01, xanchor="left", y=0.97, yanchor="top", font=dict(size=14, color=INK)),
        height=height,
        margin=dict(l=16, r=24, t=76 if legend else 52, b=40),
        showlegend=legend,
        legend=dict(orientation="h", x=0, xanchor="left", y=1.0, yanchor="bottom", font=dict(color=INK_2),
                    bgcolor="rgba(0,0,0,0)", traceorder="normal"),
        hoverlabel=dict(bgcolor="#262624", bordercolor=BASELINE, font=dict(family=FONT, color=INK)),
        bargap=0.2,
        barcornerradius=3,
    )
    axis = dict(gridcolor=GRID, gridwidth=1, zeroline=False, linecolor=BASELINE, tickfont=dict(color=MUTED),
                title_font=dict(color=MUTED, size=12))
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    return fig


def _empty_fig(message: str = "No data: waiting for poller…", height: int = 300) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                       font=dict(size=14, color=MUTED))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _style(fig, "", height, legend=False)


def _graph(figure: go.Figure) -> html.Div:
    return html.Div(dcc.Graph(figure=figure, config=_GRAPH_CONFIG),
                    style={**_CARD_STYLE, "padding": "8px", "marginBottom": "16px", "overflow": "hidden"})


def _stat_card(label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.Div(label, style={"color": MUTED, "fontSize": "11px", "marginBottom": "6px",
                                   "textTransform": "uppercase", "letterSpacing": "0.06em"}),
            html.Div(value, style={"color": INK, "fontSize": "22px", "fontWeight": "600"}),
        ],
        style={**_CARD_STYLE, "padding": "14px 20px", "flex": "1", "minWidth": "160px"},
    )


# ── Chart builders ─────────────────────────────────────────────────────────────


def _build_sentiment_ts(series: pd.DataFrame, tickers: list[str], title: str) -> go.Figure:
    if series.empty:
        return _empty_fig(height=400)
    fig = go.Figure()
    for ticker in tickers:
        sub = series[series["ticker"] == ticker].dropna(subset=["sentiment_smooth"])
        if sub.empty:
            continue
        name, color = ticker_label(ticker), ticker_color(ticker)
        fig.add_trace(go.Scatter(x=sub["processed_at"], y=sub["sentiment_smooth"], mode="lines", name=name,
                                 line=dict(color=color, width=2),
                                 hovertemplate=f"{name} ({ticker}): %{{y:+.3f}}<extra></extra>"))
        if len(tickers) > 1:
            # Label each line at its last point, so identity does not rest on colour alone.
            last = sub.iloc[-1]
            fig.add_trace(go.Scatter(x=[last["processed_at"]], y=[last["sentiment_smooth"]], mode="markers+text",
                                     marker=dict(color=color, size=8, line=dict(color=SURFACE, width=2)),
                                     text=[name], textposition="middle right", textfont=dict(color=INK_2, size=11),
                                     cliponaxis=False, showlegend=False, hoverinfo="skip"))
        if len(tickers) == 1 and sub["upper"].notna().any():
            # Thresholds are calibrated per ticker, so they are drawn only for a single ticker.
            for level, label, colour in [("upper", "HIGH", POSITIVE), ("lower", "LOW", NEGATIVE)]:
                fig.add_hline(y=float(sub[level].iloc[-1]), line_dash="dash", line_color=colour, line_width=1,
                              annotation_text=label, annotation_position="right",
                              annotation_font=dict(color=INK_2, size=11))
    fig.add_hline(y=0, line_color=BASELINE, line_width=1)
    _style(fig, title, 400)
    fig.update_layout(hovermode="x unified", margin=dict(r=110 if len(tickers) > 1 else 60))
    fig.update_yaxes(title_text="Weighted average sentiment")
    fig.update_xaxes(title_text="Time (UTC)")
    return fig


def _build_volume(series: pd.DataFrame, tickers: list[str], title: str) -> go.Figure:
    if series.empty:
        return _empty_fig(height=280)
    fig = go.Figure()
    for ticker in tickers:
        sub = series[series["ticker"] == ticker]
        name = ticker_label(ticker)
        fig.add_trace(go.Bar(x=sub["processed_at"], y=sub["headline_count"], name=name,
                             marker_color=ticker_color(ticker),
                             hovertemplate=f"{name}: %{{y:,}}<extra></extra>"))
    _style(fig, title, 280)
    fig.update_layout(barmode="stack", hovermode="x unified", barcornerradius=0)
    fig.update_yaxes(title_text="Topic-links")
    fig.update_xaxes(title_text="Time (UTC)")
    return fig


def _build_indicator_heatmap(series: pd.DataFrame, tickers: list[str], title: str) -> go.Figure:
    if series.empty:
        return _empty_fig("Not enough data for the indicator heatmap", height=220)
    codes = {"LOW": -1, "NEUTRAL": 0, "HIGH": 1}
    pivot = (
        series.assign(code=series["indicator"].map(codes))
        .pivot_table(index="ticker", columns="processed_at", values="code", aggfunc="last")
        .reindex([t for t in tickers if t in set(series["ticker"])])
    )
    states = pivot.apply(lambda col: col.map({v: k for k, v in codes.items()})).fillna("No reading")
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns, y=[ticker_label(t) for t in pivot.index], zmin=-1, zmax=1, showscale=False,
        colorscale=[[0.0, INDICATOR_COLORS["LOW"]], [0.5, INDICATOR_COLORS["NEUTRAL"]], [1.0, INDICATOR_COLORS["HIGH"]]],
        text=states.values, xgap=0, ygap=3,
        hovertemplate="<b>%{y}</b> · %{x|%d %b %H:%M}<br>%{text}<extra></extra>",
    ))
    for label in ["HIGH", "NEUTRAL", "LOW"]:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=label,
                                 marker=dict(size=10, color=INDICATOR_COLORS[label], symbol="square")))
    _style(fig, title, max(220, len(pivot) * 44 + 130))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False, autorange="reversed")  # same top-to-bottom order as the legends
    return fig


def _build_horizons(frames: dict[str, pd.DataFrame], ticker: str, title: str) -> go.Figure:
    fig = go.Figure()
    for horizon, frame in frames.items():
        sub = frame[frame["ticker"] == ticker] if not frame.empty else frame
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(x=sub["processed_at"], y=sub["sentiment_smooth"], mode="lines",
                                 line=dict(color=HORIZON_COLORS[horizon], width=2), name=HORIZON_LABELS[horizon],
                                 hovertemplate=f"{HORIZON_LABELS[horizon]}: %{{y:+.3f}}<extra></extra>"))
    if not fig.data:
        return _empty_fig(height=340)
    fig.add_hline(y=0, line_color=BASELINE, line_width=1)
    _style(fig, title, 340)
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(title_text="Weighted average sentiment")
    fig.update_xaxes(title_text="Time (UTC)")
    return fig


def _build_topics(topics: pd.DataFrame, title: str) -> go.Figure:
    if topics.empty:
        return _empty_fig(height=360)
    topics = topics.sort_values("sentiment_avg")
    fig = go.Figure(go.Bar(
        x=topics["sentiment_avg"], y=topics["topic_name"], orientation="h",
        marker_color=[NEGATIVE if v < 0 else POSITIVE for v in topics["sentiment_avg"]],
        customdata=topics["headline_count"],
        hovertemplate="%{y}<br>Average: %{x:+.3f}<br>Topic-links: %{customdata:,}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color=BASELINE, line_width=1)
    _style(fig, title, max(360, len(topics) * 28 + 90), legend=False)
    fig.update_xaxes(title_text="Volume-weighted average sentiment")
    fig.update_yaxes(showgrid=False)
    return fig


# ── Layout ─────────────────────────────────────────────────────────────────────

_dropdown_style = {"minWidth": "190px", "fontSize": "13px"}
app.layout = html.Div(
    [
        html.Div(
            [
                html.Div([
                    html.H1("GCSI Index Monitor", style={"margin": "0", "color": INK, "fontSize": "20px",
                                                         "fontWeight": "600"}),
                    html.P("Permutable AI  ·  Global Commodity Sentiment Indices  ·  Live Polling Application",
                           style={"margin": "4px 0 0", "color": MUTED, "fontSize": "12px"}),
                ]),
                html.Div(
                    [
                        dcc.Dropdown(id="ticker-dropdown", value=ALL, clearable=False, style=_dropdown_style,
                                     className="filter",
                                     options=[{"label": "All commodities", "value": ALL}]
                                     + [{"label": ticker_label(t), "value": t} for t in settings.tickers_list]),
                        dcc.Dropdown(id="horizon-dropdown", value="short_term", clearable=False, style=_dropdown_style,
                                     className="filter",
                                     options=[{"label": HORIZON_LABELS[h], "value": h} for h in HORIZONS]),
                        dcc.Dropdown(id="index-type-dropdown", value=settings.index_types_list[0], clearable=False,
                                     style=_dropdown_style, className="filter",
                                     options=[{"label": t, "value": t} for t in settings.index_types_list]),
                    ],
                    style={"display": "flex", "gap": "10px", "flexWrap": "wrap"},
                ),
            ],
            style={"padding": "20px 32px", "borderBottom": BORDER, "display": "flex", "alignItems": "center",
                   "justifyContent": "space-between", "gap": "24px", "flexWrap": "wrap"},
        ),
        html.Div(id="main-content", style={"padding": "24px 32px 8px"}),
        dcc.Interval(id="interval", interval=settings.refresh_interval_ms, n_intervals=0),
        html.Div(id="last-updated", style={"textAlign": "right", "color": MUTED, "fontSize": "11px",
                                           "padding": "0 32px 16px"}),
    ],
    style={"background": PAGE, "minHeight": "100vh", "fontFamily": FONT},
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
        return [html.P("No data available: waiting for poller…", style={"color": MUTED})], ts_label

    tickers = [t for t in settings.tickers_list if t in set(series["ticker"])] if ticker is None else [ticker]
    scope = "All commodities" if ticker is None else ticker_label(ticker)
    newest = series["processed_at"].max()
    last_day = series[series["processed_at"] > newest - pd.Timedelta(hours=24)]

    stat_row = html.Div(
        [
            _stat_card("Newest bar (UTC)", f"{newest:%d %b %H:%M}"),
            _stat_card("Topic-links (24h)", f"{int(last_day['headline_count'].sum()):,}"),
        ],
        style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "16px"},
    )

    label = f"{scope}  ·  {HORIZON_LABELS[horizon]}  ·  {index_type}"
    content = [
        stat_row,
        _graph(_build_sentiment_ts(series, tickers, f"24h weighted average sentiment  ·  {label}")),
        _graph(_build_volume(series, tickers, f"Hourly topic-links  ·  {label}")),
        _graph(_build_indicator_heatmap(series, tickers, f"Indicator, thresholds calibrated per ticker  ·  {label}")),
    ]
    if ticker is not None:
        frames = {h: fetch_frame("/sentiment/history", {**common, "sentiment_type": h}) for h in HORIZONS}
        content.append(_graph(_build_horizons(frames, ticker, f"Horizons compared  ·  {scope}  ·  {index_type}")))
    topics = pd.DataFrame(fetch_json("/topics", {**common, "sentiment_type": horizon, "limit": 15}) or [])
    content.append(_graph(_build_topics(topics, f"15 busiest topics, volume-weighted  ·  {label}")))
    return content, ts_label


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
