import numpy as np
import pandas as pd
from config import settings


def ticker_series(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive a smoothed, topic-weighted sentiment series per (ticker, sentiment_type, index_type).

    Steps:
    1. Parse processed_at to UTC-aware datetime.
    2. Add topic rows together per hour. Topics are multi-label, so the count is
       topic-links and the average is topic-weighted.
    3. sentiment_avg = sentiment_sum / headline_count per hour.
    4. sentiment_smooth = Σ sentiment_sum / Σ headline_count over a time-based
       window of settings.smoothing_hours. Hours with no news are absent from the
       data, so a row-based window would silently span more time. Readings with
       too few topic-links, or still inside the first window, are left empty.
    """
    if df.empty:
        return df

    df = df.copy()
    df["processed_at"] = pd.to_datetime(df["processed_at"], utc=True)
    keys = ["ticker", "sentiment_type", "index_type"]
    hourly = (
        df.groupby([*keys, "processed_at"], as_index=False)[["headline_count", "sentiment_sum"]]
        .sum()
        .sort_values("processed_at")
    )
    window = f"{settings.smoothing_hours}h"
    out = []
    for _, group in hourly.groupby(keys):
        rolled = group.set_index("processed_at")[["headline_count", "sentiment_sum"]].rolling(window).sum()
        group = group.assign(
            sentiment_avg=group["sentiment_sum"] / group["headline_count"],
            window_count=rolled["headline_count"].to_numpy(),
            sentiment_smooth=(rolled["sentiment_sum"] / rolled["headline_count"]).to_numpy(),
        )
        warm_up = group["processed_at"] < group["processed_at"].min() + pd.Timedelta(window)
        group.loc[(group["window_count"] < settings.min_headlines) | warm_up, "sentiment_smooth"] = np.nan
        out.append(group)
    return pd.concat(out, ignore_index=True)


def thresholds(series: pd.DataFrame) -> pd.DataFrame:
    """Upper and lower indicator thresholds per (ticker, sentiment_type, index_type)."""
    keys = ["ticker", "sentiment_type", "index_type"]
    if settings.threshold_mode == "fixed":
        out = series[keys].drop_duplicates()
        return out.assign(upper=settings.upper_threshold, lower=settings.lower_threshold)
    grouped = series.dropna(subset=["sentiment_smooth"]).groupby(keys)["sentiment_smooth"]
    return pd.DataFrame(
        {
            "upper": grouped.quantile(settings.upper_percentile),
            "lower": grouped.quantile(settings.lower_percentile),
        }
    ).reset_index()


def add_indicator(series: pd.DataFrame, limits: pd.DataFrame) -> pd.DataFrame:
    """Label each reading HIGH / NEUTRAL / LOW against its own series' thresholds."""
    if series.empty:
        return series
    series = series.merge(limits, on=["ticker", "sentiment_type", "index_type"], how="left")
    series["indicator"] = np.select(
        [series["sentiment_smooth"].isna(), series["sentiment_smooth"] >= series["upper"], series["sentiment_smooth"] <= series["lower"]],
        ["NO_READING", "HIGH", "LOW"],
        "NEUTRAL",
    )
    return series


def topic_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Volume-weighted average per topic: Σ sentiment_sum / Σ headline_count (not a mean of hourly averages)."""
    if df.empty:
        return df
    out = df.groupby("topic_name", as_index=False)[["headline_count", "sentiment_sum"]].sum()
    out["sentiment_avg"] = out["sentiment_sum"] / out["headline_count"]
    return out.sort_values("headline_count", ascending=False)
