"""Charts for the GCSI notebooks. Each function draws one figure and shows it."""

from __future__ import annotations

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import ListedColormap, TwoSlopeNorm
from matplotlib.patches import Patch

from .api import HORIZONS

POSITIVE, NEGATIVE, NEUTRAL = "#0ca30c", "#d03b3b", "#7f8c8d"
HORIZON_COLOURS = {"short_term": "#1f77b4", "medium_term": "#ff7f0e", "long_term": "#2ca02c"}
FAMILY_COLOURS = {"COMMODITY": "#3987e5", "PHYSICAL_ASSET": "#d95926", "LOCATION": "#199e70",
                  "POLICY_INSTRUMENT": "#c98500"}
KIND_COLOURS = {"Refinery": "#d95926", "Pipeline": "#3987e5", "Storage": "#199e70"}
KIND_SYMBOLS = {"Refinery": "circle", "Pipeline": "diamond", "Storage": "square"}
TYPE_LABELS = {"LNG": "LNG", "LPG_NGL": "LPG / NGL", "FERROUS_METAL_STEEL": "Ferrous metal / steel"}
LANGUAGES = {"en": "English", "ar": "Arabic", "zh": "Chinese", "es": "Spanish", "pt": "Portuguese", "ru": "Russian",
             "de": "German", "fr": "French", "ja": "Japanese", "ko": "Korean", "it": "Italian", "tr": "Turkish",
             "bg": "Bulgarian", "ro": "Romanian", "pl": "Polish", "uk": "Ukrainian", "hi": "Hindi", "id": "Indonesian",
             "fa": "Persian", "el": "Greek", "nl": "Dutch", "vi": "Vietnamese", "he": "Hebrew", "th": "Thai"}

# Display names for chart labels. Add your own; any ticker not listed is shown by its code.
TICKER_NAMES = {"BZ_COM": "Brent Crude", "QO_COM": "Gold", "ZC_COM": "Corn", "EUA_COM": "EU Carbon"}


def ticker_label(ticker: str) -> str:
    return TICKER_NAMES.get(ticker, ticker)


def _sign_colours(values) -> list[str]:
    return [NEGATIVE if v < 0 else POSITIVE for v in values]


# ── Quickstart ────────────────────────────────────────────────────────────────


def daily_horizons(daily: pd.DataFrame, title: str) -> None:
    """Daily topic-weighted average per horizon, with daily topic-links underneath."""
    fig, (ax_sent, ax_vol) = plt.subplots(2, 1, figsize=(12, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    for sentiment_type, group in daily.groupby("sentiment_type"):
        ax_sent.plot(group["date"], group["sentiment_avg"], marker="o", label=sentiment_type,
                     color=HORIZON_COLOURS.get(sentiment_type))
    ax_sent.axhline(0, color="grey", lw=0.8, ls=":")
    ax_sent.set_ylabel("Topic-weighted average")
    ax_sent.set_title(title)
    ax_sent.legend()
    volume = daily[daily["sentiment_type"] == daily["sentiment_type"].iloc[0]]
    ax_vol.bar(volume["date"], volume["headline_count"], color=NEUTRAL)
    ax_vol.set_ylabel("Topic-links")
    plt.tight_layout()
    plt.show()


def busiest_topics(by_topic: pd.DataFrame, title: str, n: int = 10) -> None:
    """Average and volume for the n busiest topics."""
    top = by_topic.nlargest(n, "headline_count").sort_values("sentiment_avg")
    fig, (ax_avg, ax_vol) = plt.subplots(1, 2, figsize=(14, 5), sharey=True, gridspec_kw={"width_ratios": [3, 2]})
    ax_avg.barh(top["topic_name"], top["sentiment_avg"], color=_sign_colours(top["sentiment_avg"]))
    ax_avg.axvline(0, color="grey", lw=0.8)
    ax_avg.set_xlabel("Topic-weighted average (short term)")
    ax_avg.set_title(title)
    ax_vol.barh(top["topic_name"], top["headline_count"], color=NEUTRAL)
    ax_vol.set_xlabel("Topic-links")
    ax_vol.set_title("News volume")
    plt.tight_layout()
    plt.show()


def stacked_daily_bars(by_day: pd.DataFrame, title: str, legend_title: str) -> None:
    """Stacked daily bars, one column of `by_day` per series."""
    by_day = by_day.sort_index()
    days = by_day.index.strftime("%d %b")
    fig, ax = plt.subplots(figsize=(14, 4))
    bottom = np.zeros(len(by_day))
    for column in by_day.columns:
        ax.bar(days, by_day[column], bottom=bottom, width=0.75, label=column)
        bottom += by_day[column].to_numpy()
    ax.set_title(title)
    ax.set_ylabel("Topic-links")
    ax.legend(title=legend_title, bbox_to_anchor=(1.01, 1), loc="upper left")
    plt.tight_layout()
    plt.show()


# ── Hourly index ──────────────────────────────────────────────────────────────


def smoothed_by_ticker(series: pd.DataFrame, tickers: list[str], title: str) -> None:
    """One panel per ticker with the smoothed series for each horizon."""
    fig, axes = plt.subplots(len(tickers), 1, figsize=(14, 3.2 * len(tickers)), sharex=True, squeeze=False)
    for ax, ticker in zip(axes[:, 0], tickers):
        for sentiment_type, group in series[series["ticker"] == ticker].groupby("sentiment_type"):
            ax.plot(group["processed_at"], group["sentiment_smooth"], lw=1.8, label=sentiment_type)
        ax.axhline(0, color="grey", lw=0.8, ls=":")
        ax.set_title(ticker_label(ticker), loc="left", fontsize=10)
    axes[0, 0].legend(loc="upper right", fontsize=9)
    fig.suptitle(title)
    axes[-1, 0].xaxis.set_major_formatter(mdates.DateFormatter("%d %b %H:%M"))
    plt.tight_layout()
    plt.show()


def volume_by_ticker(series: pd.DataFrame, tickers: list[str]) -> None:
    """Hourly topic-links per ticker, stacked (short term; every horizon has the same counts)."""
    volume = series[series["sentiment_type"] == "short_term"].pivot_table(
        index="processed_at", columns="ticker", values="headline_count", aggfunc="sum"
    ).reindex(columns=tickers)
    fig, ax = plt.subplots(figsize=(14, 3.5))
    bottom = np.zeros(len(volume))
    for ticker in tickers:
        values = volume[ticker].fillna(0).to_numpy()
        ax.bar(volume.index, values, bottom=bottom, width=1 / 24 * 0.9, label=ticker_label(ticker))
        bottom += values
    ax.set_title("Hourly topic-links by commodity")
    ax.set_ylabel("Topic-links")
    ax.legend(loc="upper left", ncol=len(tickers), fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    plt.tight_layout()
    plt.show()


def indicator_timeline(series: pd.DataFrame, tickers: list[str], sentiment_type: str = "short_term") -> None:
    """The indicator by hour, one row per ticker; blank where there is no reading."""
    codes = {"LOW": -1, "NEUTRAL": 0, "HIGH": 1}
    timeline = (
        series[series["sentiment_type"] == sentiment_type]
        .assign(code=lambda f: f["indicator"].map(codes))
        .pivot_table(index="ticker", columns="processed_at", values="code", aggfunc="last")
        .reindex(tickers)
    )
    cmap = ListedColormap([NEGATIVE, "#bdbdbd", POSITIVE])
    fig, ax = plt.subplots(figsize=(14, 0.6 * len(timeline) + 1.4))
    ax.pcolormesh(timeline.columns, range(len(timeline)), timeline.to_numpy(), cmap=cmap, vmin=-1.5, vmax=1.5,
                  shading="nearest")
    ax.set_yticks(range(len(timeline)))
    ax.set_yticklabels([ticker_label(t) for t in timeline.index])
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    handles = [Patch(color=colour, label=state) for colour, state in zip(cmap.colors[::-1], ["HIGH", "NEUTRAL", "LOW"])]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=9)
    ax.set_title(f"Indicator by hour | {sentiment_type} (blank = no reading)")
    plt.tight_layout()
    plt.show()


def smoothed_lines(lines: dict[str, pd.DataFrame], title: str) -> None:
    """Several smoothed series on one axis, e.g. one per index type."""
    fig, ax = plt.subplots(figsize=(14, 4))
    for label, smoothed in lines.items():
        ax.plot(smoothed["processed_at"], smoothed["sentiment_smooth"], label=label)
    ax.axhline(0, color="grey", lw=0.8, ls=":")
    ax.set_title(title)
    ax.legend()
    plt.tight_layout()
    plt.show()


def topic_heatmap(grid: pd.DataFrame, title: str, xlabel: str, colourbar: str = "Average sentiment",
                  annotate: bool = False) -> None:
    """Topic × time heatmap, centred on zero."""
    fig, ax = plt.subplots(figsize=(14 if not annotate else 12, 0.45 * len(grid) + 1.5))
    sns.heatmap(grid, cmap="RdYlGn", center=0, annot=annotate, fmt=".2f", linewidths=0.3, ax=ax,
                cbar_kws={"label": colourbar})
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("")
    plt.tight_layout()
    plt.show()


# ── Headline feed ─────────────────────────────────────────────────────────────


def match_mix(mix: pd.DataFrame, title: str) -> None:
    """Distinct articles and average short-term score by match type."""
    fig, (ax_rows, ax_avg) = plt.subplots(1, 2, figsize=(13, 3.5))
    ax_rows.barh(mix.index, mix["links"], color=NEUTRAL)
    ax_rows.set_title("Distinct articles by match type")
    ax_rows.set_xlabel("Articles")
    ax_avg.barh(mix.index, mix["avg_short_term"], color=_sign_colours(mix["avg_short_term"]))
    ax_avg.axvline(0, color="grey", lw=0.8)
    ax_avg.set_title("Average short-term score by match type")
    ax_avg.set_yticklabels([])
    plt.suptitle(title)
    plt.tight_layout()
    plt.show()


def own_index_by_match_type(own: pd.DataFrame, title: str, window: str = "6h") -> None:
    """Weighted rolling average per match type from your own bins, with hourly volume underneath."""
    fig, (ax, ax_vol) = plt.subplots(2, 1, figsize=(14, 6.5), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    for match_type, group in own.groupby("match_type"):
        rolled = group.set_index("bin_end")[["sentiment_sum", "headline_count"]].rolling(window).sum()
        rolled = rolled[rolled.index >= rolled.index.min() + pd.Timedelta(window)]  # drop the warm-up window
        ax.plot(rolled.index, rolled["sentiment_sum"] / rolled["headline_count"], label=match_type)
    ax.axhline(0, color="grey", lw=0.8, ls=":")
    ax.set_title(title)
    ax.legend()
    volume = own.pivot_table(index="bin_end", columns="match_type", values="headline_count", aggfunc="sum").fillna(0)
    hourly_volume = volume.resample("1h").sum()
    ax_vol.stackplot(hourly_volume.index, hourly_volume.T.to_numpy(), labels=hourly_volume.columns, alpha=0.75)
    ax_vol.set_ylabel("Topic-links per hour")
    ax_vol.set_xlabel("Receipt time (UTC)")
    plt.tight_layout()
    plt.show()


def entity_types(types: pd.DataFrame, title: str) -> None:
    """Distinct articles per matched entity type (FAMILY.TYPE), coloured by family, on a log scale."""
    families = types.index.str.split(".").str[0]
    names = [TYPE_LABELS.get(t, t.replace("_", " ").capitalize()) for t in types.index.str.split(".").str[-1]]
    fig, ax = plt.subplots(figsize=(11, 0.38 * len(types) + 1.4))
    ax.barh(names, types["articles"], color=[FAMILY_COLOURS.get(f, NEUTRAL) for f in families])
    ax.legend(handles=[Patch(color=colour, label=family.replace("_", " ").capitalize())
                       for family, colour in FAMILY_COLOURS.items() if family in set(families)], loc="lower right")
    ax.set_title(title)
    ax.set_xscale("log")  # the commodity itself usually dwarfs the rest
    ax.set_xlabel("Distinct articles (log scale)")
    plt.tight_layout()
    plt.show()


def ranked_by_score(panels: dict[str, pd.DataFrame], title: str) -> None:
    """Side-by-side article counts, each bar coloured by its average short-term score on one shared scale."""
    limit = max(max(table["avg_short_term"].abs().max() for table in panels.values()), 0.05)
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit)
    cmap = plt.get_cmap("RdYlGn")
    fig, axes = plt.subplots(1, len(panels), figsize=(7.5 * len(panels), 5.5), layout="constrained", squeeze=False)
    for ax, (panel_title, table) in zip(axes[0], panels.items()):
        ax.barh(table.index, table["articles"], color=cmap(norm(table["avg_short_term"])))
        ax.set_title(panel_title)
        ax.set_xlabel("Distinct articles")
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=axes, shrink=0.8, label="Average short-term score")
    fig.suptitle(title)
    plt.show()


def coverage(news: pd.DataFrame, title: str, n: int = 10) -> None:
    """Distinct articles by publisher country and by headline language."""
    sources = news.groupby("source_country")["link"].nunique().nlargest(n).sort_values()
    languages = news.groupby("language")["link"].nunique().nlargest(n).sort_values()
    languages.index = [LANGUAGES.get(code, code) for code in languages.index]
    fig, (ax_src, ax_lang) = plt.subplots(1, 2, figsize=(14, 4), layout="constrained")
    ax_src.barh(sources.index, sources.values, color=NEUTRAL)
    ax_src.set_title("Publisher country")
    ax_lang.barh(languages.index, languages.values, color=NEUTRAL)
    ax_lang.set_title("Headline language")
    for ax in (ax_src, ax_lang):
        ax.set_xlabel("Distinct articles")
    fig.suptitle(title)
    plt.show()


# ── Watchlist ─────────────────────────────────────────────────────────────────


def asset_map(sites: pd.DataFrame, title: str, renderer: str = "png", labels: int = 8) -> None:
    """Watchlist map: size = articles, colour = average short-term score, symbol = kind of asset."""
    import plotly.graph_objects as go

    active, quiet = sites[sites["articles"] > 0], sites[sites["articles"] == 0]
    limit = max(active["avg_short_term"].abs().max(), 0.05)
    fig = go.Figure()
    for i, (kind, symbol) in enumerate(KIND_SYMBOLS.items()):
        part = active[active["kind"] == kind]
        fig.add_trace(go.Scattergeo(
            lat=part["lat"], lon=part["lon"], text=part["label"], mode="markers", showlegend=False,
            customdata=part[["articles", "avg_short_term"]],
            hovertemplate="%{text}<br>%{customdata[0]} articles<br>average %{customdata[1]:.2f}<extra></extra>",
            marker={"symbol": symbol, "size": 9 + 32 * np.sqrt(part["articles"] / active["articles"].max()),
                    "color": part["avg_short_term"], "colorscale": "RdYlGn", "cmin": -limit, "cmax": limit,
                    "line": {"width": 0.8, "color": "#333333"}, "showscale": i == 0,
                    "colorbar": {"title": {"text": "Average<br>short-term"}, "len": 0.7}},
        ))
        # Legend entry: the shape only, since colour shows the score
        fig.add_trace(go.Scattergeo(lat=[None], lon=[None], name=kind, mode="markers",
                                    marker={"symbol": symbol, "size": 11, "color": "#ffffff", "line": {"width": 1.2}}))
    fig.add_trace(go.Scattergeo(lat=quiet["lat"], lon=quiet["lon"], text=quiet["label"], name="No articles",
                                mode="markers", marker={"size": 7, "color": "#bdbdbd", "line": {"width": 0.5}}))

    # Label the busiest sites, each on the side away from its nearest labelled neighbour
    busiest = active.nlargest(labels, "articles")
    sides = []
    for name, site in busiest.iterrows():
        others = busiest.drop(index=name)
        if others.empty:
            sides.append("middle right")
            continue
        nearest = others.loc[((others["lat"] - site["lat"]) ** 2 + (others["lon"] - site["lon"]) ** 2).idxmin()]
        sides.append("middle left" if nearest["lon"] > site["lon"] else "middle right")
    fig.add_trace(go.Scattergeo(lat=busiest["lat"], lon=busiest["lon"], text=[f" {t} " for t in busiest["label"]],
                                mode="text", textposition=sides, textfont={"size": 11, "color": "#222222"},
                                showlegend=False, hoverinfo="skip"))
    fig.update_geos(projection_type="natural earth", showcountries=True, countrycolor="#c8c8c8",
                    landcolor="#f3f3f0", showocean=True, oceancolor="#e9eff5",
                    lataxis_range=[-5, 68], lonaxis_range=[-110, 115])
    fig.update_layout(title=title, width=1100, height=500, margin={"l": 10, "r": 10, "t": 40, "b": 10},
                      legend={"orientation": "h", "y": 0.0})
    fig.show(renderer=renderer)


def asset_timeline(hits: pd.DataFrame, title: str, neutral_band: float = 0.1) -> None:
    """One row per asset with a dot per article, coloured by the sign of its short-term score, plus totals."""
    counts = hits["label"].value_counts().sort_values()
    rows_of = {label: i for i, label in enumerate(counts.index)}
    kinds = hits.drop_duplicates("label").set_index("label")["kind"]
    score = hits[HORIZONS[0]]
    colours = np.select([score > neutral_band, score < -neutral_band], [POSITIVE, NEGATIVE], "#9e9e9e")

    fig, (ax, ax_n) = plt.subplots(1, 2, figsize=(15, 0.42 * len(counts) + 1.8), sharey=True, layout="constrained",
                                   gridspec_kw={"width_ratios": [5, 1]})
    ax.scatter(hits["processed_at"], hits["label"].map(rows_of), c=colours, s=30, alpha=0.7, edgecolors="none")
    ax.set_yticks(range(len(counts)))
    ax.set_yticklabels(counts.index)
    ax.grid(axis="y", color="#ececec")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.set_xlabel("Receipt time (UTC)")
    ax.legend(handles=[Patch(color=POSITIVE, label=f"Bullish (> {neutral_band})"),
                       Patch(color="#9e9e9e", label="Neutral"),
                       Patch(color=NEGATIVE, label=f"Bearish (< -{neutral_band})")],
              loc="upper left", ncol=3, fontsize=9)
    ax.set_title(title)
    ax_n.barh(range(len(counts)), counts.values, color=[KIND_COLOURS.get(kinds[label], NEUTRAL) for label in counts.index])
    ax_n.set_xlabel("Articles")
    ax_n.legend(handles=[Patch(color=c, label=k) for k, c in KIND_COLOURS.items()], loc="lower right", fontsize=9)
    plt.show()
