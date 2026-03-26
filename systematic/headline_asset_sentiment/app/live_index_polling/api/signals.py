import pandas as pd

from config import settings


def compute_sentiment_avg(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive average sentiment and HIGH / NEUTRAL / LOW indicator from raw index data.

    Steps:
    1. Parse publication_time to UTC-aware datetime.
    2. Aggregate topic-level records to (ticker, hour) by summing sentiment fields.
    3. Compute sentiment_avg = sentiment_sum / headline_count per hour.
    4. Apply a 5-period rolling mean (sentiment_smooth) per ticker.
    5. Threshold against settings.upper_threshold / lower_threshold.

    Returns a DataFrame with one row per (ticker, hour).
    """
    if df.empty:
        return df

    df = df.copy()
    df["publication_time"] = pd.to_datetime(df["publication_time"], utc=True)

    agg = (
        df.groupby(["ticker", "publication_time"])
        .agg(
            sentiment_sum=("sentiment_sum", "sum"),
            headline_count=("headline_count", "sum"),
        )
        .reset_index()
        .sort_values(["ticker", "publication_time"])
    )

    agg["sentiment_avg"] = agg["sentiment_sum"] / agg["headline_count"].replace(0, float("nan"))
    agg["sentiment_avg"] = agg["sentiment_avg"].fillna(0.0)

    agg["sentiment_smooth"] = agg.groupby("ticker")["sentiment_avg"].transform(
        lambda x: x.rolling(5, min_periods=1).mean()
    )

    agg["indicator"] = "NEUTRAL"
    agg.loc[agg["sentiment_smooth"] >= settings.upper_threshold, "indicator"] = "HIGH"
    agg.loc[agg["sentiment_smooth"] <= settings.lower_threshold, "indicator"] = "LOW"

    return agg
