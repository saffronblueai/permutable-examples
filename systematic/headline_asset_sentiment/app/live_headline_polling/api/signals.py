import pandas as pd

from config import settings


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive LONG / SHORT / FLAT signals from a raw headline DataFrame.

    Mirrors the notebook strategy logic exactly:
    1. Parse publication_time to UTC-aware datetime.
    2. Bin to 15-minute periods and aggregate per ticker.
    3. Smooth with a 2-period (30-min equivalent) rolling mean of sentiment_mean.
    4. Apply thresholds from config to label each bin LONG / SHORT / FLAT.

    Returns an aggregated DataFrame with one row per (ticker, 15-min bin).
    """
    if df.empty:
        return df

    df = df.copy()
    df["publication_time"] = pd.to_datetime(df["publication_time"], utc=True)

    df_agg = (
        df.groupby(["ticker", pd.Grouper(key="publication_time", freq="15min")])
        .agg(
            sentiment_mean=("sentiment_score", "mean"),
            headline_count=("sentiment_score", "count"),
            conviction=(
                "sentiment_score",
                lambda s: s.sum() / s.abs().sum() if s.abs().sum() > 0 else 0.0,
            ),
        )
        .reset_index()
        .sort_values(["ticker", "publication_time"])
    )

    df_agg["signal_smooth"] = df_agg.groupby("ticker")["sentiment_mean"].transform(
        lambda x: x.rolling(2, min_periods=1).mean()
    )

    df_agg["signal"] = "FLAT"
    df_agg.loc[df_agg["signal_smooth"] >= settings.bullish_threshold, "signal"] = "LONG"
    df_agg.loc[df_agg["signal_smooth"] <= settings.bearish_threshold, "signal"] = "SHORT"

    return df_agg
