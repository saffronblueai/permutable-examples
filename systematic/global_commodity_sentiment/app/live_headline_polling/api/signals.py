from functools import cache

import numpy as np
import pandas as pd
import pycountry
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


# Feed names pycountry does not resolve; XKX is the code Plotly's maps use for Kosovo
ISO3_ALIASES = {"Turkey": "TUR", "Kosovo": "XKX"}


@cache
def _iso3(name: str) -> str | None:
    """ISO 3166 alpha-3 code for a feed country name, or None for regions such as Global or Europe."""
    if name in ISO3_ALIASES:
        return ISO3_ALIASES[name]
    try:
        return pycountry.countries.lookup(name).alpha_3
    except LookupError:
        return None


def _split(frame: pd.DataFrame, column: str, keys: list[str]) -> pd.DataFrame:
    """One row per `keys` and value of a |-separated column."""
    out = frame.assign(**{column: frame[column].str.split("|")}).explode(column)
    out[column] = out[column].str.strip()
    return out[out[column].fillna("") != ""].drop_duplicates(keys + [column])


def country_summary(df: pd.DataFrame, horizon: str, top_types: int = 3) -> pd.DataFrame:
    """Distinct articles and average score per country the headlines are about, most first.

    The feed repeats an article once per topic, so each article's score is averaged across its topics first.
    top_entity_types lists the entity types that linked most of that country's articles to the commodity.
    """
    columns = ["country", "iso3", "articles", "sentiment_avg", "top_entity_types"]
    if df.empty or "country" not in df or df["country"].isna().all():
        return pd.DataFrame(columns=columns)
    news = df.groupby("link", as_index=False).agg(
        country=("country", "first"), matched_entity_types=("matched_entity_types", "first"),
        score=(HORIZON_COLUMNS[horizon], "mean"),
    )
    by_country = _split(news.dropna(subset=["country"]), "country", ["link"])
    out = by_country.groupby("country").agg(articles=("link", "nunique"), sentiment_avg=("score", "mean"))

    types = _split(by_country.dropna(subset=["matched_entity_types"]), "matched_entity_types", ["link", "country"])
    counts = types.groupby(["country", "matched_entity_types"])["link"].nunique().rename("articles").reset_index()
    counts = counts.sort_values("articles", ascending=False).groupby("country").head(top_types)
    out["top_entity_types"] = counts.groupby("country").apply(
        lambda g: [{"entity_type": t, "articles": int(n)} for t, n in zip(g["matched_entity_types"], g["articles"])],
        include_groups=False,
    )
    out["top_entity_types"] = out["top_entity_types"].apply(lambda v: v if isinstance(v, list) else [])
    out = out.reset_index()
    out["iso3"] = out["country"].map(_iso3)
    return out[columns].sort_values("articles", ascending=False)
