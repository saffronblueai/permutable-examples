import pandas as pd

from config import settings


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive a rolling sentiment signal from GMSI raw headline data.

    Steps:
    1. Parse publication_time to UTC-aware datetime.
    2. Bin to 15-minute periods, aggregate per (country, topic).
    3. Compute mean of directional_score and semantic_sentiment_score per bin.
    4. Apply a 2-period (30-min) rolling mean for each score.
    5. Threshold directional_smooth against config thresholds to label HIGH/NEUTRAL/LOW.

    Returns a DataFrame with one row per (country, topic, 15-min bin).
    """
    if df.empty:
        return df

    df = df.copy()
    df["publication_time"] = pd.to_datetime(df["publication_time"], utc=True, format="ISO8601")

    agg = (
        df.groupby([
            "country", "topic",
            pd.Grouper(key="publication_time", freq="15min"),
        ])
        .agg(
            directional_mean=("directional_score", "mean"),
            semantic_mean=("semantic_sentiment_score", "mean"),
            headline_count=("directional_score", "count"),
        )
        .reset_index()
        .sort_values(["country", "topic", "publication_time"])
    )

    agg["directional_smooth"] = agg.groupby(["country", "topic"])["directional_mean"].transform(
        lambda x: x.rolling(2, min_periods=1).mean()
    )
    agg["semantic_smooth"] = agg.groupby(["country", "topic"])["semantic_mean"].transform(
        lambda x: x.rolling(2, min_periods=1).mean()
    )

    agg["signal"] = "NEUTRAL"
    agg.loc[agg["directional_smooth"] >= settings.upper_threshold, "signal"] = "HIGH"
    agg.loc[agg["directional_smooth"] <= settings.lower_threshold, "signal"] = "LOW"

    return agg
