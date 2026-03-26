from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db import get_db
from models import CountrySentiment, HealthResponse, RegionalRecord, SentimentPoint
from signals import compute_sentiment_indicator

app = FastAPI(
    title="Permutable AI  |  Regional Macro Sentiment API",
    description=(
        "Internal API exposing live pre-aggregated regional macro sentiment data "
        "and derived sentiment indicators from the Permutable AI regional macro feed. "
        "All data is sourced from the local SQLite database, which is continuously "
        "populated by the poller service."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Health ──────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Monitoring"])
def health():
    """Returns service status and the current row count in the database."""
    try:
        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM macro_regional_sentiment"
            ).fetchone()[0]
        return HealthResponse(status="ok", db_path=settings.db_path, row_count=count)
    except Exception:
        return HealthResponse(status="ok", db_path=settings.db_path)


# ── Raw regional data ───────────────────────────────────────────────────────────

@app.get("/regional", response_model=list[RegionalRecord], tags=["Data"])
def get_regional(
    country: Optional[str] = Query(None, description="Filter by country name"),
    hours: int = Query(24, ge=1, le=2160, description="Lookback window in hours"),
    limit: int = Query(5000, ge=1, le=50000, description="Max rows to return"),
):
    """
    Return recent regional macro sentiment records from the database.

    Each row represents one (country, hour, topic, index_type) bucket. By default
    returns the last 24 hours across all countries. Use `country` to scope to a
    single country and `hours` to widen the lookback window.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        with get_db() as conn:
            query = "SELECT * FROM macro_regional_sentiment WHERE publication_time >= ?"
            params: list = [since]
            if country:
                query += " AND country = ?"
                params.append(country)
            query += " ORDER BY publication_time DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc

    return [dict(r) for r in rows]


# ── Sentiment indicators ─────────────────────────────────────────────────────────

@app.get("/sentiment/latest", response_model=list[CountrySentiment], tags=["Sentiment"])
def get_latest_sentiment(
    hours: int = Query(12, ge=1, le=48, description="Lookback window for indicator computation"),
):
    """
    Return the latest sentiment indicator for every country in the database.

    A 5-period rolling mean of sentiment_avg is applied before thresholding to
    HIGH / NEUTRAL / LOW.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        with get_db() as conn:
            df = pd.read_sql(
                "SELECT * FROM macro_regional_sentiment WHERE publication_time >= ?",
                conn, params=(since,),
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc

    if df.empty:
        return []

    agg = compute_sentiment_indicator(df)
    now = datetime.now(timezone.utc)
    result = []

    for country, grp in agg.groupby("country"):
        last = grp.sort_values("publication_time").iloc[-1]
        result.append(
            CountrySentiment(
                country=str(country),
                publication_time=last["publication_time"],
                sentiment_avg=round(float(last["sentiment_avg"]), 4),
                sentiment_smooth=round(float(last["sentiment_smooth"]), 4),
                headline_count=int(last["headline_count"]),
                indicator=last["indicator"],
                computed_at=now,
            )
        )

    return sorted(result, key=lambda c: c.country)


@app.get("/sentiment/history", response_model=list[SentimentPoint], tags=["Sentiment"])
def get_sentiment_history(
    country: Optional[str] = Query(None, description="Filter by country name"),
    hours: int = Query(168, ge=1, le=2160, description="Lookback window in hours (default 7 days)"),
):
    """
    Return the full hourly sentiment time series for one or all countries.

    Suitable for chart rendering. Use `hours` to control the window —
    e.g. `hours=168` for 7 days of data (matching the default backfill).
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        with get_db() as conn:
            query = "SELECT * FROM macro_regional_sentiment WHERE publication_time >= ?"
            params: list = [since]
            if country:
                query += " AND country = ?"
                params.append(country)
            df = pd.read_sql(query, conn, params=params)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc

    if df.empty:
        return []

    agg = compute_sentiment_indicator(df)

    return [
        SentimentPoint(
            country=str(row.country),
            publication_time=row.publication_time,
            sentiment_avg=round(float(row.sentiment_avg), 4),
            sentiment_smooth=round(float(row.sentiment_smooth), 4),
            headline_count=int(row.headline_count),
            indicator=row.indicator,
        )
        for row in agg.itertuples()
    ]
