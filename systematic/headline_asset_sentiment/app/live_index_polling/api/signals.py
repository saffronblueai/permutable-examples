import pandas as pd

from config import settings


def compute_conviction(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive conviction ratio and HIGH / NEUTRAL / LOW indicator from raw index data.

    Steps:
    1. Parse publication_time to UTC-aware datetime.
    2. Aggregate topic-level records to (ticker, hour) by summing sentiment fields.
    3. Compute conviction_ratio = sentiment_sum / sentiment_abs_sum per hour.
    4. Apply a 5-period rolling mean (conviction_smooth) per ticker.
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
            sentiment_abs_sum=("sentiment_abs_sum", "sum"),
            headline_count=("headline_count", "sum"),
        )
        .reset_index()
        .sort_values(["ticker", "publication_time"])
    )

    agg["conviction_ratio"] = agg["sentiment_sum"] / agg["sentiment_abs_sum"].replace(0, float("nan"))
    agg["conviction_ratio"] = agg["conviction_ratio"].fillna(0.0)

    agg["conviction_smooth"] = agg.groupby("ticker")["conviction_ratio"].transform(
        lambda x: x.rolling(5, min_periods=1).mean()
    )

    agg["indicator"] = "NEUTRAL"
    agg.loc[agg["conviction_smooth"] >= settings.upper_threshold, "indicator"] = "HIGH"
    agg.loc[agg["conviction_smooth"] <= settings.lower_threshold, "indicator"] = "LOW"

    return agg
