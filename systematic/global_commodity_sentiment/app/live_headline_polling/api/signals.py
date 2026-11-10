import numpy as np
import pandas as pd
from config import settings

HORIZON_COLUMNS = {
    "short_term": "short_term_sentiment_score",
    "medium_term": "medium_term_sentiment_score",
    "long_term": "long_term_sentiment_score",
}


def binned_series(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    """
    Aggregate headlines into fixed bins per (ticker, match_type) and smooth them.

    Bins are built on processed_at (when Permutable processed the headline and made it available) and
    labelled by their END, matching the hourly index. The feed does not carry a
    publisher publication time.

    One article can sit in several topics, so headline_count counts topic-links.
    sentiment_smooth = Σ sentiment_sum / Σ headline_count over settings.smoothing_hours.
    """
    if df.empty:
        return df
    score = HORIZON_COLUMNS[horizon]
    freq = f"{settings.bin_minutes}min"
    df = df.copy()
    df["processed_at"] = pd.to_datetime(df["processed_at"], utc=True, format="ISO8601")
    df["bin_end"] = df["processed_at"].dt.floor(freq) + pd.Timedelta(freq)
    bins = (
        df.groupby(["ticker", "match_type", "bin_end"])[score]
        .agg(headline_count="size", sentiment_sum="sum", sentiment_std="std")
        .reset_index()
        .sort_values("bin_end")
    )
    bins["sentiment_std"] = bins["sentiment_std"].fillna(0.0)  # 0 for a single headline, as in the index
    bins["sentiment_avg"] = bins["sentiment_sum"] / bins["headline_count"]

    window = f"{settings.smoothing_hours}h"
    out = []
    for _, group in bins.groupby(["ticker", "match_type"]):
        rolled = group.set_index("bin_end")[["headline_count", "sentiment_sum"]].rolling(window).sum()
        group = group.assign(
            window_count=rolled["headline_count"].to_numpy(),
            sentiment_smooth=(rolled["sentiment_sum"] / rolled["headline_count"]).to_numpy(),
        )
        warm_up = group["bin_end"] < group["bin_end"].min() + pd.Timedelta(window)
        group.loc[(group["window_count"] < settings.min_headlines) | warm_up, "sentiment_smooth"] = np.nan
        out.append(group)
    return pd.concat(out, ignore_index=True)


def topic_summary(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    """Average score and row count per topic over the window."""
    if df.empty:
        return df
    score = HORIZON_COLUMNS[horizon]
    out = df.groupby("topic")[score].agg(headline_count="size", sentiment_avg="mean").reset_index()
    return out.sort_values("headline_count", ascending=False)


def match_type_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Rows, distinct articles and average score per horizon for each match type."""
    if df.empty:
        return df
    out = df.groupby("match_type").agg(
        rows=("ticker", "size"),
        articles=("link", "nunique"),
        **{f"avg_{h}": (column, "mean") for h, column in HORIZON_COLUMNS.items()},
    )
    return out.reset_index()


def entity_type_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Distinct articles per matched entity type, most first.

    matched_entity_types is a |-separated list of FAMILY.TYPE values, e.g.
    PHYSICAL_ASSET.PROCESSING_FACILITY, so each article counts once per type it names.
    """
    columns = ["entity_type", "family", "articles"]
    if df.empty or "matched_entity_types" not in df:
        return pd.DataFrame(columns=columns)
    types = df[["link", "matched_entity_types"]].dropna()
    types = types.assign(entity_type=types["matched_entity_types"].str.split("|")).explode("entity_type")
    types["entity_type"] = types["entity_type"].str.strip()
    types = types[types["entity_type"] != ""]
    out = types.groupby("entity_type")["link"].nunique().rename("articles").reset_index()
    out["family"] = out["entity_type"].str.split(".").str[0]
    return out[columns].sort_values("articles", ascending=False)
