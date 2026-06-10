import pandas as pd

from config import settings


def compute_sentiment_indicator(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive rolling sentiment indicators from GMSI hourly index data.

    Steps:
    1. Parse publication_time to UTC-aware datetime.
    2. Aggregate to (country, topic, sentiment_type, index_type, hour)
       by summing sentiment fields.
    3. Compute sentiment_avg = sentiment_sum / headline_count per hour.
    4. Compute activity_weighted = sentiment_sum / sentiment_abs_sum per hour
       (volume-adjusted directional score).
    5. Apply a 5-period rolling mean of sentiment_avg per country/sentiment_type/index_type.
    6. Threshold against config thresholds to label HIGH / NEUTRAL / LOW.

    Returns a DataFrame with one row per (country, sentiment_type, index_type, hour).
    """
    if df.empty:
        return df

    df = df.copy()
    df["publication_time"] = pd.to_datetime(df["publication_time"], utc=True, format="ISO8601")

    agg = (
        df.groupby(["country", "topic", "sentiment_type", "index_type", "publication_time"])
        .agg(
            sentiment_sum=("sentiment_sum", "sum"),
            sentiment_abs_sum=("sentiment_abs_sum", "sum"),
            headline_count=("headline_count", "sum"),
        )
        .reset_index()
        .sort_values(["country", "sentiment_type", "index_type", "publication_time"])
    )

    agg["sentiment_avg"] = (
        agg["sentiment_sum"] / agg["headline_count"].replace(0, float("nan"))
    ).fillna(0.0)

    agg["activity_weighted"] = (
        agg["sentiment_sum"] / agg["sentiment_abs_sum"].replace(0, float("nan"))
    ).fillna(0.0)

    agg["sentiment_smooth"] = agg.groupby(
        ["country", "topic", "sentiment_type", "index_type"]
    )["sentiment_avg"].transform(
        lambda x: x.rolling(5, min_periods=1).mean()
    )

    agg["indicator"] = "NEUTRAL"
    agg.loc[agg["sentiment_smooth"] >= settings.upper_threshold, "indicator"] = "HIGH"
    agg.loc[agg["sentiment_smooth"] <= settings.lower_threshold, "indicator"] = "LOW"

    return agg
