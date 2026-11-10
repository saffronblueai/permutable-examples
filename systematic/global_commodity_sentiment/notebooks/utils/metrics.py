"""Aggregation for the GCSI notebooks: pooling index bars, smoothing, the indicator and headline counts."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .api import HORIZONS, LIST_SEPARATOR, TOPIC_SEPARATOR

# ── Hourly index ──────────────────────────────────────────────────────────────


def pool(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Combine index rows into larger buckets (hours → days, topics → drivers, ...).

    Counts and sums add. The sample standard deviation is pooled exactly: each row's sum of squares is
    rebuilt as (n - 1)·std² + n·mean², summed, and turned back into a sample standard deviation.
    Averaging hourly standard deviations would be wrong.
    """
    n = frame["headline_count"].astype(float)
    mean = frame["sentiment_sum"] / n
    sumsq = (n - 1).clip(lower=0) * frame["sentiment_std"].fillna(0.0) ** 2 + n * mean**2
    out = (
        frame.assign(_sumsq=sumsq)
        .groupby(keys, as_index=False, observed=True)[["headline_count", "sentiment_sum", "_sumsq"]]
        .sum()
    )
    n = out["headline_count"].astype(float)
    out["sentiment_avg"] = out["sentiment_sum"] / n
    variance = (out["_sumsq"] - n * out["sentiment_avg"] ** 2) / (n - 1)
    out["sentiment_std"] = np.sqrt(variance.where(n > 1, 0.0).clip(lower=0.0))
    return out.drop(columns="_sumsq")


def processed_date(processed_at: pd.Series) -> pd.Series:
    """UTC date the headlines were processed. A bar stamped 00:00 covers 23:00–24:00 of the previous day."""
    return (processed_at - pd.Timedelta(hours=1)).dt.floor("D").dt.tz_localize(None)


def driver(topic_name: pd.Series) -> pd.Series:
    """The L1 driver, the middle part of Sector::Driver::Topic."""
    return topic_name.str.split(TOPIC_SEPARATOR).str[1]


def ticker_series(frame: pd.DataFrame, window: str = "24h", min_headlines: int = 5) -> pd.DataFrame:
    """Ticker-level hourly series with a time-based weighted rolling average.

    Topics are added per hour (topic-weighted), then `Σ sentiment_sum / Σ headline_count` over the window.
    Windows with fewer than `min_headlines` topic-links, and the warm-up window, have no reading.
    """
    hourly = (
        frame.groupby(["ticker", "sentiment_type", "processed_at"], as_index=False)[["headline_count", "sentiment_sum"]]
        .sum()
        .sort_values("processed_at")
    )
    out = []
    for _, group in hourly.groupby(["ticker", "sentiment_type"]):
        rolled = group.set_index("processed_at")[["headline_count", "sentiment_sum"]].rolling(window).sum()
        group = group.assign(
            window_count=rolled["headline_count"].values,
            sentiment_avg=group["sentiment_sum"] / group["headline_count"],
            sentiment_smooth=(rolled["sentiment_sum"] / rolled["headline_count"]).values,
        )
        warm_up = group["processed_at"] < group["processed_at"].min() + pd.Timedelta(window)
        group.loc[(group["window_count"] < min_headlines) | warm_up, "sentiment_smooth"] = np.nan
        out.append(group)
    return pd.concat(out, ignore_index=True) if out else hourly


def add_indicator(frame: pd.DataFrame, mode: str = "percentile", upper_pct: float = 0.90, lower_pct: float = 0.10,
                  fixed_upper: float = 0.15, fixed_lower: float = -0.15) -> pd.DataFrame:
    """HIGH / NEUTRAL / LOW from the smoothed series, with thresholds per ticker and horizon.

    mode='percentile' calibrates the thresholds from each series' own history; mode='fixed' uses fixed values.
    """
    frame = frame.copy()
    frame["indicator"] = "NO READING"
    for _, group in frame.groupby(["ticker", "sentiment_type"]):
        values = group["sentiment_smooth"].dropna()
        if values.empty:
            continue
        if mode == "percentile":
            upper, lower = values.quantile(upper_pct), values.quantile(lower_pct)
        else:
            upper, lower = fixed_upper, fixed_lower
        idx = group.index[group["sentiment_smooth"].notna()]
        frame.loc[idx, "indicator"] = np.select(
            [frame.loc[idx, "sentiment_smooth"] >= upper, frame.loc[idx, "sentiment_smooth"] <= lower],
            ["HIGH", "LOW"], "NEUTRAL",
        )
        frame.loc[group.index, ["upper", "lower"]] = upper, lower
    return frame


def daily_topic_average(index_rows: pd.DataFrame, min_headlines: int = 5, top: int = 15) -> pd.DataFrame:
    """Topic × processed day average for the busiest topics; cells under `min_headlines` topic-links are blank."""
    rows = index_rows.assign(day=(index_rows["processed_at"] - pd.Timedelta(hours=1)).dt.floor("D"))
    grid = rows.groupby(["topic_name", "day"])[["sentiment_sum", "headline_count"]].sum()
    avg = (grid["sentiment_sum"] / grid["headline_count"]).where(grid["headline_count"] >= min_headlines).unstack()
    busiest = rows.groupby("topic_name")["headline_count"].sum().nlargest(top).index
    avg = avg.reindex(busiest)
    avg.columns = avg.columns.strftime("%d %b")
    return avg


# ── Headline feed ─────────────────────────────────────────────────────────────


def own_index(feed: pd.DataFrame, horizon: str = HORIZONS[0], freq: str = "15min") -> pd.DataFrame:
    """Your own index from the feed: bins on processed_at, labelled by their end, like the hourly index."""
    binned = feed.assign(bin_end=feed["processed_at"].dt.floor(freq) + pd.Timedelta(freq))
    out = binned.groupby(["ticker", "match_type", "bin_end"]).agg(
        headline_count=(horizon, "size"),
        sentiment_sum=(horizon, "sum"),
        sentiment_std=(horizon, "std"),
    ).reset_index()
    out["sentiment_std"] = out["sentiment_std"].fillna(0.0)  # matches the index: 0 for a single headline
    out["sentiment_avg"] = out["sentiment_sum"] / out["headline_count"]
    return out


def windowed_topic_average(feed: pd.DataFrame, horizon: str = HORIZONS[0], freq: str = "6h",
                           min_headlines: int = 5, top: int = 12) -> pd.DataFrame:
    """Topic × time-window average score for the busiest topics; cells under `min_headlines` rows are blank."""
    busiest = feed["topic"].value_counts().head(top).index
    rows = feed[feed["topic"].isin(busiest)].assign(window=lambda f: f["processed_at"].dt.floor(freq))
    grid = rows.groupby(["topic", "window"])[horizon].agg(["mean", "size"])
    avg = grid["mean"].where(grid["size"] >= min_headlines).unstack()
    avg.columns = avg.columns.strftime("%d %b\n%H:00")
    return avg


def articles(feed: pd.DataFrame) -> pd.DataFrame:
    """One row per article, with its short-term score averaged across the topics it appears under."""
    fields = ["matched_entity_types", "matched_entities", "country", "source_country", "language"]
    return feed.groupby("link", as_index=False).agg(
        **{field: (field, "first") for field in fields}, score=(HORIZONS[0], "mean")
    )


def explode_list(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """One row per article and value of a |-separated column."""
    out = frame.assign(**{column: frame[column].str.split(LIST_SEPARATOR)}).explode(column)
    out[column] = out[column].str.strip()
    return out[out[column].fillna("") != ""].drop_duplicates(["link", column])


def by_value(frame: pd.DataFrame, column: str, n: int = 12) -> pd.DataFrame:
    """Distinct articles and average short-term score for the n most frequent values, smallest first for barh.

    `column` can be a |-separated list column, such as country or matched_entities.
    """
    out = explode_list(frame, column).groupby(column).agg(articles=("link", "nunique"), avg_short_term=("score", "mean"))
    return out.nlargest(n, "articles").sort_values("articles")


def watchlist_hits(feed: pd.DataFrame, watchlist: dict) -> pd.DataFrame:
    """Feed rows that name a watchlist asset, one row per article and asset.

    The feed repeats an article once per topic, so the most likely topic is kept and the scores are averaged.
    `watchlist` maps the entity name, as it appears in matched_entities, to (label, kind, latitude, longitude).
    """
    rows = feed.assign(asset=feed["matched_entities"].str.split(LIST_SEPARATOR)).explode("asset")
    rows = rows[rows["asset"].isin(watchlist.keys())]
    hits = (
        rows.sort_values("topic_probability", ascending=False)
        .groupby(["link", "asset"], as_index=False)
        .agg(processed_at=("processed_at", "first"), topic=("topic", "first"), country=("country", "first"),
             headline=("headline", "first"), source_name=("source_name", "first"),
             **{horizon: (horizon, "mean") for horizon in HORIZONS})
    )
    hits["label"] = hits["asset"].map(lambda asset: watchlist[asset][0])
    hits["kind"] = hits["asset"].map(lambda asset: watchlist[asset][1])
    return hits


def watchlist_sites(hits: pd.DataFrame, watchlist: dict) -> pd.DataFrame:
    """Every watchlist asset with its location, article count and average short-term score."""
    summary = hits.groupby("asset").agg(articles=("link", "nunique"), avg_short_term=(HORIZONS[0], "mean"))
    sites = pd.DataFrame.from_dict(watchlist, orient="index", columns=["label", "kind", "lat", "lon"]).join(summary)
    sites["articles"] = sites["articles"].fillna(0).astype(int)
    return sites
