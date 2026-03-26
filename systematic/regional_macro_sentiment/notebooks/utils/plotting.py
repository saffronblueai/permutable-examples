"""
Reusable Plotly plotting utilities for Regional Macro Sentiment analysis.

All functions accept a raw ``df`` DataFrame sourced from the
``macro_regional_sentiment`` SQLite table and return a ``go.Figure`` ready
to call ``.show()`` on.

Expected columns in ``df``:
    publication_time  (datetime, UTC-aware)
    country           (str, lower-case)
    topic_name        (str)
    sentiment_avg     (float, −1 to +1)
    sentiment_sum     (float)
    sentiment_std     (float)
    headline_count    (int)
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── Shared style constants ────────────────────────────────────────────────────

_PALETTE = [
    "#636EFA",
    "#EF553B",
    "#00CC96",
    "#AB63FA",
    "#FFA15A",
    "#19D3F3",
    "#FF6692",
    "#B6E880",
    "#FF97FF",
    "#FECB52",
]

_DARK_BG = "#1a1a2e"
_MENU_BG = "#1e1e30"
_MENU_BORDER = "#555"
_GRID = "#333"
_LABEL_FONT = dict(color="#aaa", size=11)
_MENU_FONT = dict(color="#eee", size=12)


def _hex_rgba(hex_color: str, alpha: float = 0.12) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _dropdown_menu(buttons: list, x: float, y: float = 1.08, direction: str = "down") -> dict:
    return dict(
        buttons=buttons,
        direction=direction,
        x=x,
        xanchor="right",
        y=y,
        yanchor="top",
        bgcolor=_MENU_BG,
        bordercolor=_MENU_BORDER,
        font=_MENU_FONT,
        showactive=True,
    )


def _label_annotation(text: str, x: float, y: float = 1.07) -> dict:
    return dict(
        text=text,
        x=x,
        xref="paper",
        y=y,
        yref="paper",
        showarrow=False,
        font=_LABEL_FONT,
        xanchor="right",
    )


# ── 1. Choropleth avg sentiment map ──────────────────────────────────────────────


def plot_sentiment_map(
    df: pd.DataFrame,
    time_windows: list[tuple[str, pd.Timedelta]] | None = None,
    height: int = 520,
) -> go.Figure:
    """Choropleth world map of average macro sentiment by country.

    Two independent dropdowns:
    - **Period** (bottom-left, upward) — restyles z-values on all traces.
    - **Topic** (bottom-left, upward, below Period) — toggles trace visibility.

    Avg Sentiment = ``sentiment_sum / headline_count`` over the selected period,
    normalised to [−1, +1].

    Parameters
    ----------
    df:
        Raw ``macro_regional_sentiment`` DataFrame.
    time_windows:
        List of ``(label, timedelta)`` pairs defining the period buttons.
        Defaults to Last Hour / Last Day / Last Week.
    height:
        Figure height in pixels.

    Returns
    -------
    go.Figure
    """
    if time_windows is None:
        time_windows = [
            ("Last Hour", pd.Timedelta(hours=1)),
            ("Last Day", pd.Timedelta(hours=24)),
            ("Last Week", pd.Timedelta(days=7)),
        ]

    now = df["publication_time"].max()
    topics = ["All Topics"] + sorted(df["topic_name"].dropna().unique().tolist())
    all_countries = sorted(df["country"].dropna().unique().tolist())
    all_countries_titled = [c.title() for c in all_countries]

    def _compute_z(period_td: pd.Timedelta, topic: str) -> list:
        sub = df[df["publication_time"] >= now - period_td]
        if topic != "All Topics":
            sub = sub[sub["topic_name"] == topic]
        agg = sub.groupby("country").agg(
            sentiment_sum=("sentiment_sum", "sum"),
            headline_count=("headline_count", "sum"),
        )
        avg_sentiment = agg["sentiment_sum"] / agg["headline_count"]
        return [float(avg_sentiment.get(c, float("nan"))) for c in all_countries]

    # Pre-compute z for every (period, topic) pair
    period_zs = {p_idx: [_compute_z(p_td, t) for t in topics] for p_idx, (_, p_td) in enumerate(time_windows)}

    fig = go.Figure()
    for t_idx, topic in enumerate(topics):
        fig.add_trace(
            go.Choropleth(
                locations=all_countries_titled,
                locationmode="country names",
                z=period_zs[0][t_idx],
                zmin=-1,
                zmax=1,
                colorscale=[[0, "#c0392b"], [0.5, "#f5f5f5"], [1, "#2ecc71"]],
                colorbar=dict(title="Avg Sentiment", tickfont=dict(color="#ccc")),
                hovertemplate="<b>%{location}</b><br>Avg Sentiment: %{z:.3f}<extra></extra>",
                visible=(t_idx == 0),
                name=topic,
            )
        )

    n = len(topics)

    topic_buttons = [
        dict(
            label=topic,
            method="update",
            args=[
                {"visible": [j == t_idx for j in range(n)]},
                {"title": f"Regional Macro Sentiment — {topic}"},
            ],
        )
        for t_idx, topic in enumerate(topics)
    ]

    period_buttons = [
        dict(
            label=p_label,
            method="update",
            args=[
                {"z": period_zs[p_idx]},
                {"title": f"Regional Macro Sentiment — {p_label}"},
            ],
        )
        for p_idx, (p_label, _) in enumerate(time_windows)
    ]

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=_DARK_BG,
        title=f"Regional Macro Sentiment — All Topics | Last Hour  ({now.strftime('%Y-%m-%d %H:%M UTC')})",
        geo=dict(
            showframe=False,
            showcoastlines=True,
            coastlinecolor="#444",
            showland=True,
            landcolor="#2a2a3e",
            showocean=True,
            oceancolor=_DARK_BG,
            showcountries=True,
            countrycolor=_GRID,
            bgcolor=_DARK_BG,
            projection_type="natural earth",
        ),
        updatemenus=[
            dict(
                buttons=period_buttons,
                direction="up",
                x=0.01,
                xanchor="left",
                y=0.13,
                yanchor="bottom",
                bgcolor=_MENU_BG,
                bordercolor=_MENU_BORDER,
                font=_MENU_FONT,
                showactive=True,
            ),
            dict(
                buttons=topic_buttons,
                direction="up",
                x=0.01,
                xanchor="left",
                y=0.01,
                yanchor="bottom",
                bgcolor=_MENU_BG,
                bordercolor=_MENU_BORDER,
                font=_MENU_FONT,
                showactive=True,
            ),
        ],
        annotations=[
            dict(
                text="Period:",
                x=0.01,
                xref="paper",
                y=0.21,
                yref="paper",
                showarrow=False,
                font=_LABEL_FONT,
                xanchor="left",
            ),
            dict(
                text="Topic:",
                x=0.01,
                xref="paper",
                y=0.09,
                yref="paper",
                showarrow=False,
                font=_LABEL_FONT,
                xanchor="left",
            ),
        ],
        height=height,
        margin=dict(l=0, r=0, t=80, b=0),
    )
    return fig


# ── 2. Sentiment time series + headline count ─────────────────────────────────


def plot_sentiment_time_series(
    df: pd.DataFrame,
    aggregated: pd.DataFrame,
    countries: list[str],
    height: int = 560,
) -> go.Figure:
    """Two-row subplot: sentiment avg ±1 std band (top) + headline count (bottom).

    Two independent dropdowns:
    - **Topic** (left) — restyles x/y data on all traces.
    - **Country** (right) — toggles trace visibility.

    Parameters
    ----------
    df:
        Raw ``macro_regional_sentiment`` DataFrame (used for per-topic
        re-aggregation when a specific topic is selected).
    aggregated:
        ``(country, publication_time)`` level DataFrame containing
        ``sentiment_avg``, ``sentiment_std``, and ``headline_count``.
        Used as the "All Topics" data source (pass ``hourly`` or ``ts``).
    countries:
        Ordered list of country name strings to include (lower-case).
    height:
        Figure height in pixels.

    Returns
    -------
    go.Figure
    """
    topics = ["All Topics"] + sorted(df["topic_name"].dropna().unique().tolist())

    def _series(topic: str, country: str):
        """Return (x, lower, upper, avg, count) for a country/topic pair."""
        if topic == "All Topics":
            sub = aggregated[aggregated["country"] == country].sort_values("publication_time")
        else:
            sub = (
                df[(df["topic_name"] == topic) & (df["country"] == country)]
                .groupby("publication_time")
                .agg(
                    sentiment_avg=("sentiment_avg", "mean"),
                    sentiment_sum=("sentiment_sum", "sum"),
                    headline_count=("headline_count", "sum"),
                    sentiment_std=("sentiment_std", "mean"),
                )
                .reset_index()
                .sort_values("publication_time")
            )
        lower = (sub["sentiment_avg"] - sub["sentiment_std"].fillna(0)).tolist()
        upper = (sub["sentiment_avg"] + sub["sentiment_std"].fillna(0)).tolist()
        return (
            sub["publication_time"].tolist(),
            lower,
            upper,
            sub["sentiment_avg"].tolist(),
            sub["headline_count"].tolist(),
        )

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("Sentiment Avg  (\u00b11 std band)", "Headline Count \u2014 Hourly"),
    )

    trace_map: dict[str, list[int]] = {}
    for i, country in enumerate(countries):
        x, lower, upper, avg, count = _series("All Topics", country)
        color = _PALETTE[i % len(_PALETTE)]
        fill_color = _hex_rgba(color)
        idx0 = len(fig.data)

        fig.add_trace(
            go.Scatter(
                x=x,
                y=lower,
                mode="lines",
                line=dict(width=0),
                showlegend=False,
                hoverinfo="skip",
                legendgroup=country,
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=upper,
                mode="lines",
                fill="tonexty",
                fillcolor=fill_color,
                line=dict(width=0),
                showlegend=False,
                hoverinfo="skip",
                legendgroup=country,
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=avg,
                mode="lines",
                name=country.title(),
                line=dict(width=1.6, color=color),
                legendgroup=country,
                hovertemplate=(
                    f"<b>{country.title()}</b><br>" "%{x|%b %d %H:%M}<br>Sentiment: %{y:.3f}<extra></extra>"
                ),
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=count,
                mode="lines",
                name=country.title(),
                showlegend=False,
                line=dict(width=1.6, color=color),
                legendgroup=country,
                hovertemplate=(f"<b>{country.title()}</b><br>" "%{x|%b %d %H:%M}<br>Headlines: %{y}<extra></extra>"),
            ),
            row=2,
            col=1,
        )

        trace_map[country] = list(range(idx0, idx0 + 4))

    fig.add_hline(y=0, line=dict(color="#555", width=0.8, dash="dash"), row=1, col=1)

    n_traces = len(fig.data)

    country_buttons = [dict(label="All Countries", method="restyle", args=[{"visible": [True] * n_traces}])]
    for country in countries:
        vis = [False] * n_traces
        for idx in trace_map[country]:
            vis[idx] = True
        country_buttons.append(
            dict(
                label=country.title(),
                method="restyle",
                args=[{"visible": vis}],
            )
        )

    topic_buttons = []
    for topic in topics:
        x_all, y_all = [], []
        for country in countries:
            x, lower, upper, avg, count = _series(topic, country)
            x_all.extend([x, x, x, x])
            y_all.extend([lower, upper, avg, count])
        topic_buttons.append(
            dict(
                label=topic,
                method="restyle",
                args=[{"x": x_all, "y": y_all}],
            )
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=_DARK_BG,
        plot_bgcolor=_DARK_BG,
        title="Sentiment Avg & Headline Count by Country",
        yaxis=dict(title="Sentiment Avg", gridcolor=_GRID),
        yaxis2=dict(title="Headline Count", gridcolor=_GRID),
        xaxis2=dict(tickformat="%b %d", tickangle=30, gridcolor=_GRID),
        legend=dict(font=dict(size=9), orientation="h", y=-0.1),
        updatemenus=[
            _dropdown_menu(topic_buttons, x=0.60),
            _dropdown_menu(country_buttons, x=1.0),
        ],
        annotations=[
            _label_annotation("Topic:", x=0.35),
            _label_annotation("Country:", x=0.73),
        ],
        height=height,
        margin=dict(l=60, r=20, t=90, b=70),
    )
    return fig


# ── 3. Avg sentiment heatmap (country × time, topic dropdown) ───────────────────


def plot_sentiment_heatmap(
    df: pd.DataFrame,
    countries: list[str],
    rolling_window: int = 5,
    height: int | None = None,
) -> go.Figure:
    """Country × time rolling avg sentiment heatmap with a topic dropdown.

    Avg Sentiment = ``rolling_sum(sentiment_sum) / rolling_sum(headline_count)``
    over ``rolling_window`` hours. NaN filled with 0.

    One ``go.Heatmap`` trace per topic; the topic dropdown toggles visibility.

    Parameters
    ----------
    df:
        Raw ``macro_regional_sentiment`` DataFrame.
    countries:
        Ordered list of country names (lower-case). Determines y-axis order.
    rolling_window:
        Number of hours for the rolling sum window.
    height:
        Figure height in pixels. Defaults to ``max(300, len(countries)*28 + 130)``.

    Returns
    -------
    go.Figure
    """
    if height is None:
        height = max(300, len(countries) * 28 + 130)

    col_times = sorted(df["publication_time"].unique())
    x_labels = [pd.Timestamp(t).strftime("%b %d %H:%M") for t in col_times]
    y_labels = [c.title() for c in countries]
    topics = ["All Topics"] + sorted(df["topic_name"].dropna().unique().tolist())

    def _sentiment_matrix(topic: str) -> list[list[float]]:
        src = df if topic == "All Topics" else df[df["topic_name"] == topic]
        agg = (
            src[src["country"].isin(countries)]
            .groupby(["country", "publication_time"])
            .agg(
                sentiment_sum=("sentiment_sum", "sum"),
                headline_count=("headline_count", "sum"),
            )
            .reset_index()
        )
        p_ss = (
            agg.pivot_table(
                index="publication_time",
                columns="country",
                values="sentiment_sum",
                aggfunc="sum",
            )
            .reindex(index=col_times, columns=countries)
            .fillna(0)
        )
        p_hc = (
            agg.pivot_table(
                index="publication_time",
                columns="country",
                values="headline_count",
                aggfunc="sum",
            )
            .reindex(index=col_times, columns=countries)
            .fillna(0)
        )
        avg_sentiment = (
            (
                p_ss.rolling(window=rolling_window, min_periods=1).sum()
                / p_hc.rolling(window=rolling_window, min_periods=1).sum()
            )
            .fillna(0)
            .T
        )
        return [[round(v, 4) for v in row] for row in avg_sentiment.values.tolist()]

    # Day-boundary x-axis ticks
    seen_dates: set = set()
    tick_vals, tick_text = [], []
    for lbl, t in zip(x_labels, col_times):
        d = pd.Timestamp(t).date()
        if d not in seen_dates:
            seen_dates.add(d)
            tick_vals.append(lbl)
            tick_text.append(pd.Timestamp(t).strftime("%b %d"))

    fig = go.Figure()
    for t_idx, topic in enumerate(topics):
        fig.add_trace(
            go.Heatmap(
                z=_sentiment_matrix(topic),
                x=x_labels,
                y=y_labels,
                colorscale="RdYlGn",
                zmid=0,
                zmin=-1,
                zmax=1,
                colorbar=dict(title="Avg Sentiment", tickfont=dict(color="#ccc")),
                hovertemplate="<b>%{y}</b><br>%{x}<br>Avg Sentiment: %{z:.3f}<extra></extra>",
                visible=(t_idx == 0),
                name=topic,
            )
        )

    n = len(topics)
    topic_buttons = [
        dict(
            label=topic,
            method="update",
            args=[
                {"visible": [j == t_idx for j in range(n)]},
                {"title": (f"{rolling_window}-Hour Rolling Avg Sentiment \u2014 {topic}")},
            ],
        )
        for t_idx, topic in enumerate(topics)
    ]

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=_DARK_BG,
        plot_bgcolor=_DARK_BG,
        title=f"{rolling_window}-Hour Rolling Avg Sentiment \u2014 Country \u00d7 Hour  |  All Topics",
        xaxis=dict(
            tickvals=tick_vals,
            ticktext=tick_text,
            tickangle=30,
            tickfont=dict(size=9),
            gridcolor=_GRID,
        ),
        yaxis=dict(tickfont=dict(size=9), gridcolor=_GRID, autorange="reversed"),
        updatemenus=[_dropdown_menu(topic_buttons, x=1.0, y=1.15)],
        annotations=[_label_annotation("Topic:", x=0.73, y=1.14)],
        height=height,
        margin=dict(l=130, r=20, t=110, b=70),
    )
    return fig


# ── 4. Real-Time Avg Sentiment table ─────────────────────────────────────────────

def plot_sentiment_table(
    df: pd.DataFrame,
    rolling_window: int = 5,
    upper_threshold: float = 0.15,
    lower_threshold: float = -0.15,
    height: int = 480,
) -> go.Figure:
    """    Side-by-side tables of High Negative (left) and High Positive (right) avg sentiment countries.

    One pair of ``go.Table`` traces per topic (negative | positive); a topic
    dropdown toggles which pair is visible. Neutral countries are excluded.
    The figure is fixed-height and scrollable — rows beyond the visible area
    can be reached by scrolling inside the table.

    Avg Sentiment = ``rolling_sum(sentiment_sum) / rolling_sum(headline_count)``
    over ``rolling_window`` hours, NaN filled with 0.

    Parameters
    ----------
    df:
        Raw ``macro_regional_sentiment`` DataFrame.
    rolling_window:
        Hours for the rolling avg sentiment window (default 5).
    upper_threshold:
        Above this threshold → **High Positive** (default 0.15).
    lower_threshold:
        Below this threshold → **High Negative** (default −0.15).
    height:
        Fixed figure height in pixels (default 480). Content beyond this
        height is reachable by scrolling within the table.

    Returns
    -------
    go.Figure
    """

    def _splits(topic: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return (negative_df, positive_df) sorted strongest-first."""
        src = df if topic == "All Topics" else df[df["topic_name"] == topic]
        agg = (
            src.groupby(["country", "publication_time"])
            .agg(
                sentiment_sum=("sentiment_sum", "sum"),
                headline_count=("headline_count", "sum"),
            )
            .reset_index()
            .sort_values(["country", "publication_time"])
        )
        agg["avg_sentiment"] = (
            agg.groupby("country")
            .apply(
                lambda g: (
                    g["sentiment_sum"].rolling(rolling_window, min_periods=1).sum()
                    / g["headline_count"].rolling(rolling_window, min_periods=1).sum()
                )
            )
            .reset_index(level=0, drop=True)
            .fillna(0)
        )
        latest = (
            agg.sort_values("publication_time")
            .groupby("country")
            .last()
            .reset_index()[["country", "publication_time", "avg_sentiment", "headline_count"]]
        )
        neg = (
            latest[latest["avg_sentiment"] <= lower_threshold]
            .sort_values("avg_sentiment", ascending=True)   # most negative first
        )
        pos = (
            latest[latest["avg_sentiment"] >= upper_threshold]
            .sort_values("avg_sentiment", ascending=False)  # most positive first
        )
        return neg, pos

    def _make_table(data: pd.DataFrame, color: str, domain_x: list, visible: bool, name: str) -> go.Table:
        n = len(data)
        conv_col = "<b>Avg Sentiment ({}h)</b>".format(rolling_window)
        return go.Table(
            domain=dict(x=domain_x, y=[0, 1]),
            header=dict(
                values=["<b>Country</b>", conv_col, "<b>Headlines</b>"],
                fill_color=_MENU_BG,
                font=dict(color="#eee", size=11),
                align="left",
                line_color=_GRID,
            ),
            cells=dict(
                values=[
                    data["country"].str.title().tolist(),
                    data["avg_sentiment"].round(4).tolist(),
                    data["headline_count"].astype(int).tolist(),
                ],
                fill_color=[[_DARK_BG] * n, [color] * n, [_DARK_BG] * n],
                font=dict(color="#eee", size=10),
                align="left",
                line_color=_GRID,
            ),
            visible=visible,
            name=name,
        )

    topics = ["All Topics"] + sorted(df["topic_name"].dropna().unique().tolist())

    fig = go.Figure()
    for t_idx, topic in enumerate(topics):
        neg, pos = _splits(topic)
        visible = t_idx == 0
        fig.add_trace(_make_table(neg, "#c0392b", [0, 0.48], visible, f"{topic} — High Negative"))
        fig.add_trace(_make_table(pos, "#2ecc71", [0.52, 1.0], visible, f"{topic} — High Positive"))

    n_topics = len(topics)
    n_traces = n_topics * 2

    topic_buttons = [
        dict(
            label=topic,
            method="update",
            args=[
                {"visible": [
                    i // 2 == t_idx for i in range(n_traces)
                ]},
                {
                    "title": (
                        f"Real-Time Avg Sentiment \u2014 {rolling_window}-Hour Rolling | {topic}"
                    )
                },
            ],
        )
        for t_idx, topic in enumerate(topics)
    ]

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=_DARK_BG,
        title=(
            f"Real-Time Avg Sentiment \u2014 {rolling_window}-Hour Rolling"
            " | All Topics"
        ),
        annotations=[
            dict(
                text="<b>High Negative Avg Sentiment</b>",
                x=0.24, xref="paper", y=1.04, yref="paper",
                showarrow=False, font=dict(color="#c0392b", size=12), xanchor="center",
            ),
            dict(
                text="<b>High Positive Avg Sentiment</b>",
                x=0.76, xref="paper", y=1.04, yref="paper",
                showarrow=False, font=dict(color="#2ecc71", size=12), xanchor="center",
            ),
            _label_annotation("Topic:", x=0.73, y=1.11),
        ],
        updatemenus=[_dropdown_menu(topic_buttons, x=1.0, y=1.12)],
        height=height,
        margin=dict(l=20, r=20, t=100, b=20),
    )
    return fig
