from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
from config import settings, ticker_label
from dash import Dash, Input, Output, callback, dash_table, dcc, html

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
MATCH_COLORS = {"EXPLICIT": "#3987e5", "RELATED_ENTITY": "#d95926", "MACROECONOMIC": "#199e70"}
MATCH_ORDER = ["EXPLICIT", "RELATED_ENTITY", "MACROECONOMIC"]
POSITIVE, NEGATIVE = "#0ca30c", "#d03b3b"
FAMILY_COLORS = {"COMMODITY": "#3987e5", "PHYSICAL_ASSET": "#d95926", "LOCATION": "#199e70",
                 "POLICY_INSTRUMENT": "#c98500"}
TYPE_LABELS = {"LNG": "LNG", "LPG_NGL": "LPG / NGL", "FERROUS_METAL_STEEL": "Ferrous metal / steel"}

HORIZONS = ["short_term", "medium_term", "long_term"]
HORIZON_LABELS = {"short_term": "Short term", "medium_term": "Medium term", "long_term": "Long term"}

_CARD_STYLE = {"background": SURFACE, "border": BORDER, "borderRadius": "10px"}
_GRAPH_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}

app = Dash(__name__, title="GCSI Headline Monitor")


# ── Helpers ────────────────────────────────────────────────────────────────────


def fetch_json(path: str, params: dict | None = None) -> list | dict | None:
    try:
        r = requests.get(f"{settings.api_url}{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


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


def _stat_card(label: str, value: str, dot: str | None = None) -> html.Div:
    marker = [html.Span(style={"display": "inline-block", "width": "8px", "height": "8px", "borderRadius": "50%",
                               "background": dot, "marginRight": "6px"})] if dot else []
    return html.Div(
        [
            html.Div(marker + [label], style={"color": MUTED, "fontSize": "11px", "marginBottom": "6px",
                                              "textTransform": "uppercase", "letterSpacing": "0.06em"}),
            html.Div(value, style={"color": INK, "fontSize": "22px", "fontWeight": "600"}),
        ],
        style={**_CARD_STYLE, "padding": "14px 20px", "flex": "1", "minWidth": "160px"},
    )


def _match_groups(bins: pd.DataFrame):
    """Match types in a fixed order, so each keeps its colour and legend position."""
    present = set(bins["match_type"])
    for match_type in [m for m in MATCH_ORDER if m in present] + sorted(present - set(MATCH_ORDER)):
        yield match_type, bins[bins["match_type"] == match_type]


# ── Chart builders ─────────────────────────────────────────────────────────────


def _build_smoothed(bins: pd.DataFrame, title: str) -> go.Figure:
    if bins.empty:
        return _empty_fig(height=380)
    fig = go.Figure()
    for match_type, sub in _match_groups(bins):
        fig.add_trace(go.Scatter(x=sub["bin_end"], y=sub["sentiment_smooth"], mode="lines", name=match_type,
                                 line=dict(color=MATCH_COLORS.get(match_type, MUTED), width=2),
                                 hovertemplate=f"{match_type}: %{{y:+.3f}}<extra></extra>"))
    fig.add_hline(y=0, line_color=BASELINE, line_width=1)
    _style(fig, title, 380)
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(title_text="Weighted average score")
    fig.update_xaxes(title_text="Bin end, processed time (UTC)")
    return fig


def _build_volume(bins: pd.DataFrame, title: str) -> go.Figure:
    if bins.empty:
        return _empty_fig(height=280)
    fig = go.Figure()
    for match_type, sub in _match_groups(bins):
        fig.add_trace(go.Bar(x=sub["bin_end"], y=sub["headline_count"], name=match_type,
                             marker_color=MATCH_COLORS.get(match_type, MUTED),
                             hovertemplate=f"{match_type}: %{{y:,}}<extra></extra>"))
    _style(fig, title, 280)
    fig.update_layout(barmode="stack", hovermode="x unified", barcornerradius=0)
    fig.update_yaxes(title_text="Rows (headline × topic)")
    fig.update_xaxes(title_text="Bin end, processed time (UTC)")
    return fig


def _build_topics(topics: pd.DataFrame, title: str) -> go.Figure:
    if topics.empty:
        return _empty_fig(height=360)
    topics = topics.sort_values("sentiment_avg")
    fig = go.Figure(go.Bar(
        x=topics["sentiment_avg"], y=topics["topic"], orientation="h",
        marker_color=[NEGATIVE if v < 0 else POSITIVE for v in topics["sentiment_avg"]],
        customdata=topics["headline_count"],
        hovertemplate="%{y}<br>Average: %{x:+.3f}<br>Rows: %{customdata:,}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color=BASELINE, line_width=1)
    _style(fig, title, max(360, len(topics) * 28 + 90), legend=False)
    fig.update_xaxes(title_text="Average score")
    fig.update_yaxes(showgrid=False)
    return fig


def _type_label(entity_type: str) -> str:
    name = entity_type.split(".")[-1]
    return TYPE_LABELS.get(name, name.replace("_", " ").capitalize())


def _build_entity_types(types: pd.DataFrame, title: str) -> go.Figure:
    """Distinct articles per matched entity type (FAMILY.TYPE), one colour per family, log scale."""
    if types.empty:
        return _empty_fig(height=360)
    types = types.sort_values("articles")
    names = [_type_label(t) for t in types["entity_type"]]
    fig = go.Figure()
    for family, color in FAMILY_COLORS.items():
        mask = (types["family"] == family).to_numpy()
        if not mask.any():
            continue
        fig.add_trace(go.Bar(
            x=types["articles"][mask], y=[n for n, m in zip(names, mask) if m], orientation="h",
            name=family.replace("_", " ").capitalize(), marker_color=color,
            hovertemplate="%{y}<br>Articles: %{x:,}<extra></extra>",
        ))
    _style(fig, title, max(360, len(types) * 26 + 110))
    fig.update_xaxes(type="log", title_text="Distinct articles (log scale)")
    fig.update_yaxes(showgrid=False, categoryorder="array", categoryarray=names)
    return fig


def _build_country_map(countries: pd.DataFrame, title: str, labels: int = 6, min_articles: int = 10) -> go.Figure:
    """Each country the news is about, filled by its average score; article counts and entity types on hover.

    Countries with fewer than `min_articles` articles are filled grey, since a handful of headlines gives a noisy
    average. Regions such as Global or Europe are left off the map and counted in the title.
    """
    if countries.empty:
        return _empty_fig(height=520)
    mapped = countries[countries["iso3"].notna() & countries["sentiment_avg"].notna()].copy()
    off_map = int(countries.loc[countries["iso3"].isna(), "articles"].sum())
    if off_map:
        title += f"  ·  {off_map:,} articles tagged a region (e.g. Global, Europe), not on the map"
    if mapped.empty:
        return _empty_fig("No country tags in the window", height=520)
    mapped["types"] = mapped["top_entity_types"].apply(
        lambda types: "<br>".join(f"{_type_label(t['entity_type'])}: {t['articles']:,}" for t in types) or "n/a")
    hover = ("<b>%{customdata[0]}</b><br>%{customdata[1]:,} articles<br>Average %{customdata[2]:+.3f}"
             "<br><br>Linked by<br>%{customdata[3]}<extra></extra>")
    fields = ["country", "articles", "sentiment_avg", "types"]
    scored, sparse = mapped[mapped["articles"] >= min_articles], mapped[mapped["articles"] < min_articles]
    limit = max(scored["sentiment_avg"].abs().max(), 0.05) if not scored.empty else 0.05
    fig = go.Figure()
    fig.add_trace(go.Choropleth(
        locations=sparse["iso3"], locationmode="ISO-3", z=[0] * len(sparse), customdata=sparse[fields],
        colorscale=[[0, "#4a4a46"], [1, "#4a4a46"]], showscale=False, hovertemplate=hover,
        marker_line=dict(color=PAGE, width=0.5),
    ))
    fig.add_trace(go.Choropleth(
        locations=scored["iso3"], locationmode="ISO-3", z=scored["sentiment_avg"], customdata=scored[fields],
        colorscale="RdYlGn", zmin=-limit, zmax=limit, hovertemplate=hover, marker_line=dict(color=PAGE, width=0.5),
        colorbar=dict(title=dict(text="Average<br>score", font=dict(color=MUTED)), len=0.7,
                      tickfont=dict(color=MUTED), outlinewidth=0),
    ))
    # Name the busiest countries ("Iran, Islamic Republic of" → "Iran") on their centroids
    busiest = mapped.head(labels)
    fig.add_trace(go.Scattergeo(
        locations=busiest["iso3"], locationmode="ISO-3", mode="text", hoverinfo="skip",
        text="<b>" + busiest["country"].str.split(",").str[0].str.replace("Russian Federation", "Russia") + "</b>",
        textfont=dict(size=11, color=PAGE, family=FONT),
    ))
    if not sparse.empty:
        fig.add_annotation(text=f"Grey: fewer than {min_articles} articles", xref="paper", yref="paper", x=0.01,
                           y=0.02, showarrow=False, font=dict(size=11, color=MUTED))
    _style(fig, title, 520, legend=False)
    fig.update_geos(projection_type="natural earth", bgcolor=SURFACE, showframe=False,
                    showland=True, landcolor="#232321", showocean=True, oceancolor="#151514",
                    showcountries=True, countrycolor="#3a3a37", coastlinecolor="#3a3a37", lataxis_range=[-50, 80])
    fig.update_layout(margin=dict(l=8, r=8, t=52, b=8))
    return fig


def _headline_table(rows: list[dict], horizon: str) -> dash_table.DataTable:
    score = f"{horizon}_sentiment_score"
    data = [
        {
            "processed": pd.Timestamp(r["processed_at"]).strftime("%d %b %H:%M"),
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
        columns=[{"name": c, "id": c} for c in ["processed", "match_type", "topic", "score", "headline", "source"]],
        style_as_list_view=True,
        style_header={"backgroundColor": SURFACE, "color": MUTED, "fontWeight": "600", "fontSize": "11px",
                      "textTransform": "uppercase", "letterSpacing": "0.06em", "borderBottom": BORDER},
        style_cell={"backgroundColor": SURFACE, "color": INK_2, "borderBottom": BORDER, "fontSize": "12px",
                    "fontFamily": FONT, "textAlign": "left", "whiteSpace": "normal", "height": "auto",
                    "maxWidth": "520px", "padding": "8px 10px"},
        style_data_conditional=[
            {"if": {"column_id": "score"}, "color": INK, "fontVariantNumeric": "tabular-nums"},
            {"if": {"column_id": "headline"}, "color": INK},
        ],
        page_size=10,
    )


# ── Layout ─────────────────────────────────────────────────────────────────────

_dropdown_style = {"minWidth": "190px", "fontSize": "13px"}
app.layout = html.Div(
    [
        html.Div(
            [
                html.Div([
                    html.H1("GCSI Headline Monitor", style={"margin": "0", "color": INK, "fontSize": "20px",
                                                            "fontWeight": "600"}),
                    html.P("Permutable AI  ·  Global Commodity Sentiment Indices  ·  Headline Feed",
                           style={"margin": "4px 0 0", "color": MUTED, "fontSize": "12px"}),
                ]),
                html.Div(
                    [
                        dcc.Dropdown(id="ticker-dropdown", value=settings.tickers_list[0], clearable=False,
                                     style=_dropdown_style, className="filter",
                                     options=[{"label": ticker_label(t), "value": t} for t in settings.tickers_list]),
                        dcc.Dropdown(id="horizon-dropdown", value="short_term", clearable=False, style=_dropdown_style,
                                     className="filter",
                                     options=[{"label": HORIZON_LABELS[h], "value": h} for h in HORIZONS]),
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
    Input("interval", "n_intervals"),
)
def update_content(ticker: str, horizon: str, n: int):
    ts_label = datetime.now(timezone.utc).strftime("Last updated: %Y-%m-%d %H:%M UTC")
    hours = settings.dashboard_hours

    bins = pd.DataFrame(fetch_json("/sentiment/bins", {"ticker": ticker, "horizon": horizon, "hours": hours}) or [])
    if bins.empty:
        return [html.P("No data available: waiting for poller…", style={"color": MUTED})], ts_label
    bins["bin_end"] = pd.to_datetime(bins["bin_end"], utc=True)

    mix = pd.DataFrame(fetch_json("/match-types", {"ticker": ticker, "hours": hours}) or [])
    topics = pd.DataFrame(fetch_json("/topics", {"ticker": ticker, "horizon": horizon, "hours": hours}) or [])
    types = pd.DataFrame(fetch_json("/entity-types", {"ticker": ticker, "hours": hours}) or [])
    countries = pd.DataFrame(fetch_json("/countries", {"ticker": ticker, "horizon": horizon, "hours": hours}) or [])
    strongest = fetch_json("/headlines", {"ticker": ticker, "hours": 6, "sort": "strongest", "limit": 20}) or []

    cards = [_stat_card("Rows (window)", f"{int(mix['rows'].sum()):,}" if not mix.empty else "0"),
             _stat_card("Distinct articles", f"{int(mix['articles'].sum()):,}" if not mix.empty else "0")]
    if not mix.empty:
        mix = mix.set_index("match_type").reindex([m for m in MATCH_ORDER if m in set(mix["match_type"])])
        for match_type, row in mix.iterrows():
            avg = row[f"avg_{horizon}"]
            cards.append(_stat_card(f"{match_type} avg", f"{avg:+.3f}" if pd.notna(avg) else "n/a",
                                    dot=MATCH_COLORS.get(match_type, MUTED)))

    label = f"{ticker_label(ticker)}  ·  {HORIZON_LABELS[horizon]}"
    return [
        html.Div(cards, style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "16px"}),
        _graph(_build_smoothed(bins, f"Weighted average by match type (own bins)  ·  {label}")),
        _graph(_build_volume(bins, f"Rows per bin  ·  {label}")),
        _graph(_build_topics(topics, f"15 busiest topics  ·  {label}")),
        _graph(_build_entity_types(types, f"What linked the news to the commodity  ·  {ticker_label(ticker)}")),
        _graph(_build_country_map(countries, f"Where the news is about  ·  {label}")),
        html.Div(
            [
                html.H3("Strongest headlines, last 6 hours",
                        style={"color": INK, "fontSize": "14px", "fontWeight": "600", "margin": "4px 4px 12px"}),
                _headline_table(strongest, horizon),
            ],
            style={**_CARD_STYLE, "padding": "16px", "marginBottom": "16px"},
        ),
    ], ts_label


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
