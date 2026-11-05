from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
from config import settings
from dash import Dash, Input, Output, callback, dash_table, dcc, html

# ── Colour palettes ────────────────────────────────────────────────────────────
MATCH_COLORS = {"EXPLICIT": "#3498db", "RELATED_ENTITY": "#9b59b6", "MACROECONOMIC": "#f39c12"}
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

app = Dash(__name__, title="GCSI Headline Monitor")


# ── Helpers ────────────────────────────────────────────────────────────────────


def fetch_json(path: str, params: dict | None = None) -> list | dict | None:
    try:
        r = requests.get(f"{settings.api_url}{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


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


def _build_smoothed(bins: pd.DataFrame, title: str) -> go.Figure:
    if bins.empty:
        return _empty_fig(height=360)
    fig = go.Figure()
    for match_type, sub in bins.groupby("match_type"):
        fig.add_trace(go.Scatter(x=sub["bin_end"], y=sub["sentiment_smooth"], mode="lines", name=match_type,
                                 line=dict(color=MATCH_COLORS.get(match_type, "#ccc"), width=2)))
    fig.add_hline(y=0, line_dash="dot", line_color="#555", line_width=1)
    fig.update_layout(**_CHART_BASE, title=title, xaxis_title="Bin end, receipt time (UTC)",
                      yaxis_title="Weighted avg score", legend=_LEGEND, height=360, margin=dict(l=0, r=160, t=60, b=40))
    return fig


def _build_volume(bins: pd.DataFrame, title: str) -> go.Figure:
    if bins.empty:
        return _empty_fig(height=260)
    fig = go.Figure()
    for match_type, sub in bins.groupby("match_type"):
        fig.add_trace(go.Bar(x=sub["bin_end"], y=sub["headline_count"], name=match_type,
                             marker_color=MATCH_COLORS.get(match_type, "#ccc")))
    fig.update_layout(**_CHART_BASE, barmode="stack", title=title, xaxis_title="Bin end, receipt time (UTC)",
                      yaxis_title="Rows (headline × topic)", legend=_LEGEND, height=260,
                      margin=dict(l=0, r=160, t=60, b=40))
    return fig


def _build_topics(topics: pd.DataFrame, title: str) -> go.Figure:
    if topics.empty:
        return _empty_fig(height=340)
    topics = topics.sort_values("sentiment_avg")
    fig = go.Figure(go.Bar(
        x=topics["sentiment_avg"], y=topics["topic"], orientation="h",
        marker_color=["#e74c3c" if v < 0 else "#2ecc71" for v in topics["sentiment_avg"]],
        customdata=topics["headline_count"], hovertemplate="%{y}<br>Avg: %{x:.3f}<br>Rows: %{customdata}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#555", line_dash="dash", line_width=1)
    fig.update_layout(**_CHART_BASE, title=title, xaxis_title="Average score",
                      height=max(340, len(topics) * 28 + 80), margin=dict(l=0, r=0, t=50, b=30))
    return fig


def _headline_table(rows: list[dict], horizon: str) -> dash_table.DataTable:
    score = f"{horizon}_sentiment_score"
    data = [
        {
            "received": pd.Timestamp(r["extraction_time"]).strftime("%d %b %H:%M"),
            "match_type": r.get("match_type"),
            "topic": r.get("topic"),
            "score": round(r[score], 3) if r.get(score) is not None else None,
            "headline": r.get("headline"),
            "source": r.get("source_name"),
        }
        for r in rows
    ]
    return dash_table.DataTable(
        data=data,
        columns=[{"name": c, "id": c} for c in ["received", "match_type", "topic", "score", "headline", "source"]],
        style_header={"backgroundColor": "#1e1e30", "color": "#ccc", "fontWeight": "700", "border": "1px solid #2e2e45"},
        style_cell={"backgroundColor": "#1a1a2e", "color": "#ddd", "border": "1px solid #2e2e45", "fontSize": "12px",
                    "textAlign": "left", "whiteSpace": "normal", "height": "auto", "maxWidth": "520px"},
        style_data_conditional=[
            {"if": {"filter_query": "{score} > 0", "column_id": "score"}, "color": "#2ecc71"},
            {"if": {"filter_query": "{score} < 0", "column_id": "score"}, "color": "#e74c3c"},
        ],
        page_size=10,
    )


# ── Layout ─────────────────────────────────────────────────────────────────────

_dropdown_style = {"minWidth": "180px", "color": "#000", "fontSize": "13px"}
app.layout = html.Div(
    [
        html.Div(
            [
                html.Div([
                    html.H1("GCSI Headline Monitor", style={"margin": "0", "color": "#fff", "fontSize": "20px"}),
                    html.P("Permutable AI  ·  Global Commodity Sentiment Indices  ·  Headline Feed",
                           style={"margin": "2px 0 0", "color": "#aaa", "fontSize": "12px"}),
                ]),
                html.Div(
                    [
                        dcc.Dropdown(id="ticker-dropdown", value=settings.tickers_list[0], clearable=False,
                                     style=_dropdown_style,
                                     options=[{"label": t, "value": t} for t in settings.tickers_list]),
                        dcc.Dropdown(id="horizon-dropdown", value="short_term", clearable=False, style=_dropdown_style,
                                     options=[{"label": h, "value": h} for h in HORIZONS]),
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
    Input("interval", "n_intervals"),
)
def update_content(ticker: str, horizon: str, n: int):
    ts_label = datetime.now(timezone.utc).strftime("Last updated: %Y-%m-%d %H:%M UTC")
    hours = settings.dashboard_hours

    bins = pd.DataFrame(fetch_json("/sentiment/bins", {"ticker": ticker, "horizon": horizon, "hours": hours}) or [])
    if bins.empty:
        return [html.P("No data available: waiting for poller…", style={"color": "#888"})], ts_label
    bins["bin_end"] = pd.to_datetime(bins["bin_end"], utc=True)

    mix = pd.DataFrame(fetch_json("/match-types", {"ticker": ticker, "hours": hours}) or [])
    topics = pd.DataFrame(fetch_json("/topics", {"ticker": ticker, "horizon": horizon, "hours": hours}) or [])
    strongest = fetch_json("/headlines", {"ticker": ticker, "hours": 6, "sort": "strongest", "limit": 20}) or []

    cards = [_stat_card("Rows (window)", f"{int(mix['rows'].sum()):,}" if not mix.empty else "0"),
             _stat_card("Distinct articles", f"{int(mix['articles'].sum()):,}" if not mix.empty else "0")]
    for row in mix.itertuples():
        avg = getattr(row, f"avg_{horizon}")
        cards.append(_stat_card(f"{row.match_type} avg", f"{avg:+.3f}" if avg is not None else "n/a",
                                color=MATCH_COLORS.get(row.match_type, "#ccc")))

    label = f"{ticker}  |  {horizon}"
    return [
        html.Div(cards, style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "20px"}),
        dcc.Graph(figure=_build_smoothed(bins, f"{label}  |  weighted average by match type (own bins)"),
                  style={"marginBottom": "16px"}),
        dcc.Graph(figure=_build_volume(bins, f"{label}  |  rows per bin"), style={"marginBottom": "24px"}),
        dcc.Graph(figure=_build_topics(topics, f"{label}  |  15 busiest topics"), style={"marginBottom": "24px"}),
        html.H3("Strongest headlines, last 6 hours", style={"color": "#ccc", "fontSize": "15px"}),
        _headline_table(strongest, horizon),
    ], ts_label


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
