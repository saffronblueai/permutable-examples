import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from config import settings
from db import get_db
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from models import HealthResponse, IndexRecord, SentimentPoint, TickerSentiment, TopicSentiment
from signals import add_indicator, thresholds, ticker_series, topic_summary

app = FastAPI(
    title="Permutable AI  |  GCSI Hourly Index API",
    description=(
        "Local API exposing Global Commodity Sentiment Indices (GCSI) hourly index data "
        "and derived sentiment indicators. All data is read from the local SQLite "
        "database, which the poller service keeps up to date."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

SENTIMENT_TYPE = Query("short_term", description="short_term | medium_term | long_term")
INDEX_TYPE = Query("COMBINED", description="EXPLICIT | RELATED_ENTITY | MACROECONOMIC | COMBINED")


def _since(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _load(hours: int, sentiment_type: str, index_type: str, ticker: Optional[str] = None) -> pd.DataFrame:
    query = "SELECT * FROM gcsi_index WHERE processed_at >= ? AND sentiment_type = ? AND index_type = ?"
    params: list = [_since(hours), sentiment_type, index_type]
    if ticker:
        query += " AND ticker = ?"
        params.append(ticker)
    try:
        with get_db() as conn:
            return pd.read_sql(query, conn, params=params)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc


def _series(hours: int, sentiment_type: str, index_type: str, ticker: Optional[str] = None) -> pd.DataFrame:
    """Smoothed series with indicator thresholds calibrated on CALIBRATION_HOURS of history."""
    df = _load(max(hours, settings.calibration_hours), sentiment_type, index_type, ticker)
    if df.empty:
        return df
    series = ticker_series(df)
    series = add_indicator(series, thresholds(series))
    return series[series["processed_at"] >= pd.Timestamp(_since(hours))]


def _clean(value):
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else value


def _point(row) -> dict:
    return {
        "ticker": row.ticker,
        "sentiment_type": row.sentiment_type,
        "index_type": row.index_type,
        "processed_at": row.processed_at,
        "headline_count": int(row.headline_count),
        "sentiment_avg": round(float(row.sentiment_avg), 4),
        "sentiment_smooth": _clean(round(float(row.sentiment_smooth), 4)),
        "window_count": int(row.window_count),
        "upper": _clean(float(row.upper)),
        "lower": _clean(float(row.lower)),
        "indicator": row.indicator,
    }


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Monitoring"])
def health():
    """Returns service status, the row count and the newest stored bar."""
    try:
        with get_db() as conn:
            count, latest = conn.execute("SELECT COUNT(*), MAX(processed_at) FROM gcsi_index").fetchone()
        return HealthResponse(status="ok", db_path=settings.db_path, row_count=count, latest_processed_at=latest)
    except Exception:
        return HealthResponse(status="ok", db_path=settings.db_path)


# ── Raw index data ─────────────────────────────────────────────────────────────

@app.get("/index", response_model=list[IndexRecord], tags=["Data"])
def get_index(
    ticker: Optional[str] = Query(None, description="Filter by ticker"),
    sentiment_type: Optional[str] = Query(None, description="Filter by horizon"),
    index_type: Optional[str] = Query(None, description="Filter by index type"),
    hours: int = Query(24, ge=1, le=2160, description="Lookback window in hours"),
    limit: int = Query(5000, ge=1, le=50000, description="Max rows to return"),
):
    """
    Return stored hourly index rows, newest first.

    Each row is one (ticker, topic, index_type, sentiment_type, hour) bar.
    processed_at is the END of the hour (UTC).
    """
    query = "SELECT * FROM gcsi_index WHERE processed_at >= ?"
    params: list = [_since(hours)]
    for column, value in (("ticker", ticker), ("sentiment_type", sentiment_type), ("index_type", index_type)):
        if value:
            query += f" AND {column} = ?"
            params.append(value)
    query += " ORDER BY processed_at DESC LIMIT ?"
    params.append(limit)
    try:
        with get_db() as conn:
            rows = conn.execute(query, params).fetchall()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc
    return [dict(r) for r in rows]


# ── Sentiment indicators ───────────────────────────────────────────────────────

@app.get("/sentiment/latest", response_model=list[TickerSentiment], tags=["Sentiment"])
def get_latest_sentiment(sentiment_type: str = SENTIMENT_TYPE, index_type: str = INDEX_TYPE):
    """
    Latest smoothed sentiment and indicator for every ticker.

    sentiment_smooth = Σ sentiment_sum / Σ headline_count over SMOOTHING_HOURS.
    HIGH / LOW thresholds are calibrated per ticker and horizon (THRESHOLD_MODE).
    """
    series = _series(settings.smoothing_hours * 3, sentiment_type, index_type)
    if series.empty:
        return []
    now = datetime.now(timezone.utc)
    latest = series.sort_values("processed_at").groupby("ticker").tail(1)
    return sorted(
        (TickerSentiment(**_point(row), computed_at=now) for row in latest.itertuples()),
        key=lambda item: item.ticker,
    )


@app.get("/sentiment/history", response_model=list[SentimentPoint], tags=["Sentiment"])
def get_sentiment_history(
    ticker: Optional[str] = Query(None, description="Filter by ticker"),
    sentiment_type: str = SENTIMENT_TYPE,
    index_type: str = INDEX_TYPE,
    hours: int = Query(168, ge=1, le=2160, description="Lookback window in hours (default 7 days)"),
):
    """Hourly smoothed sentiment series with indicator, suitable for charting."""
    series = _series(hours, sentiment_type, index_type, ticker)
    return [SentimentPoint(**_point(row)) for row in series.sort_values("processed_at").itertuples()]


@app.get("/topics", response_model=list[TopicSentiment], tags=["Sentiment"])
def get_topics(
    ticker: Optional[str] = Query(None, description="Filter by ticker"),
    sentiment_type: str = SENTIMENT_TYPE,
    index_type: str = INDEX_TYPE,
    hours: int = Query(168, ge=1, le=2160, description="Lookback window in hours"),
    limit: int = Query(15, ge=1, le=200, description="Number of topics, busiest first"),
):
    """Volume-weighted average sentiment by topic over the window, busiest topics first."""
    summary = topic_summary(_load(hours, sentiment_type, index_type, ticker)).head(limit)
    return [
        TopicSentiment(topic_name=r.topic_name, headline_count=int(r.headline_count), sentiment_avg=round(float(r.sentiment_avg), 4))
        for r in summary.itertuples()
    ]
