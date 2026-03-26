import pandas as pd

from config import settings


def compute_sentiment_indicator(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive a rolling sentiment indicator (HIGH / NEUTRAL / LOW) from raw regional data.

    Steps:
    1. Parse publication_time to UTC-aware datetime.
    2. Aggregate topic-level records to (country, hour) by averaging sentiment fields.
    3. Apply a 5-period rolling mean of sentiment_avg per country (sentiment_smooth).
    4. Threshold against settings.upper_threshold / lower_threshold.

    Unlike the asset index, the regional macro API provides sentiment_avg directly
    (already normalised to [−1, +1]), so no conviction ratio calculation is needed.

    Returns a DataFrame with one row per (country, hour).
    """
    if df.empty:
        return df

    df = df.copy()
    df["publication_time"] = pd.to_datetime(df["publication_time"], utc=True)

    agg = (
        df.groupby(["country", "publication_time"])
        .agg(
            sentiment_avg=("sentiment_avg", "mean"),
            sentiment_sum=("sentiment_sum", "sum"),
            headline_count=("headline_count", "sum"),
            sentiment_std=("sentiment_std", "mean"),
        )
        .reset_index()
        .sort_values(["country", "publication_time"])
    )

    agg["sentiment_smooth"] = agg.groupby("country")["sentiment_avg"].transform(
        lambda x: x.rolling(5, min_periods=1).mean()
    )

    agg["indicator"] = "NEUTRAL"
    agg.loc[agg["sentiment_smooth"] >= settings.upper_threshold, "indicator"] = "HIGH"
    agg.loc[agg["sentiment_smooth"] <= settings.lower_threshold, "indicator"] = "LOW"

    return agg
