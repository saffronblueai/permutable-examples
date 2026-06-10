from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db import get_db
from models import CountrySentiment, GmsiIndexRecord, HealthResponse, SentimentPoint
from signals import compute_sentiment_indicator

app = FastAPI(
    title="Permutable AI  |  GMSI Hourly Index API",
    description=(
        "Internal API exposing live GMSI hourly index data and derived sentiment indicators "
        "from the Permutable AI Global Macro Sentiment Indices feed. "
        "All data is sourced from the local SQLite database populated by the poller."
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
            count = conn.execute("SELECT COUNT(*) FROM gmsi_index").fetchone()[0]
        return HealthResponse(status="ok", db_path=settings.db_path, row_count=count)
    except Exception:
        return HealthResponse(status="ok", db_path=settings.db_path)


# ── Raw index records ───────────────────────────────────────────────────────────


@app.get("/gmsi", response_model=list[GmsiIndexRecord], tags=["Data"])
def get_gmsi(
    country: Optional[str] = Query(None, description="Filter by ISO-2 country code"),
    topic: Optional[str] = Query(None, description="Filter by GMSI topic name"),
    sentiment_type: Optional[str] = Query(None, description="directional or semantic_sentiment"),
    index_type: Optional[str] = Query(None, description="COMBINED, DOMESTIC, or INTERNATIONAL"),
    hours: int = Query(24, ge=1, le=2160, description="Lookback window in hours"),
    limit: int = Query(5000, ge=1, le=50000, description="Max rows to return"),
):
    """
    Return recent GMSI hourly index records from the database.

    Each row represents one (country, topic, sentiment_type, index_type, hour) bucket.
    By default returns the last 24 hours across all configured dimensions.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        with get_db() as conn:
            query = "SELECT * FROM gmsi_index WHERE publication_time >= ?"
            params: list = [since]
            if country:
                query += " AND country = ?"
                params.append(country)
            if topic:
                query += " AND topic = ?"
                params.append(topic)
            if sentiment_type:
                query += " AND sentiment_type = ?"
                params.append(sentiment_type)
            if index_type:
                query += " AND index_type = ?"
                params.append(index_type)
            query += " ORDER BY publication_time DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc

    return [dict(r) for r in rows]


# ── Sentiment indicators ────────────────────────────────────────────────────────


@app.get("/sentiment/latest", response_model=list[CountrySentiment], tags=["Sentiment"])
def get_latest_sentiment(
    sentiment_type: Optional[str] = Query("directional", description="directional or semantic_sentiment"),
    index_type: Optional[str] = Query("COMBINED", description="COMBINED, DOMESTIC, or INTERNATIONAL"),
    hours: int = Query(12, ge=1, le=48, description="Lookback window for indicator computation"),
):
    """
    Return the latest sentiment indicator for every (country, topic) combination.

    A 5-period rolling mean of sentiment_avg is computed before thresholding to
    HIGH / NEUTRAL / LOW. Filter by sentiment_type and index_type to compare views.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        with get_db() as conn:
            query = "SELECT * FROM gmsi_index WHERE publication_time >= ?"
            params: list = [since]
            if sentiment_type:
                query += " AND sentiment_type = ?"
                params.append(sentiment_type)
            if index_type:
                query += " AND index_type = ?"
                params.append(index_type)
            df = pd.read_sql(query, conn, params=params)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc

    if df.empty:
        return []

    agg = compute_sentiment_indicator(df)
    now = datetime.now(timezone.utc)
    result = []

    for (country, topic, stype, itype), grp in agg.groupby(["country", "topic", "sentiment_type", "index_type"]):
        last = grp.sort_values("publication_time").iloc[-1]
        result.append(
            CountrySentiment(
                country=str(country),
                topic=str(topic),
                sentiment_type=str(stype),
                index_type=str(itype),
                publication_time=last["publication_time"],
                sentiment_avg=round(float(last["sentiment_avg"]), 4),
                sentiment_smooth=round(float(last["sentiment_smooth"]), 4),
                activity_weighted=round(float(last["activity_weighted"]), 4),
                headline_count=int(last["headline_count"]),
                indicator=last["indicator"],
                computed_at=now,
            )
        )

    return sorted(result, key=lambda s: (s.country, s.topic, s.sentiment_type))


@app.get("/sentiment/history", response_model=list[SentimentPoint], tags=["Sentiment"])
def get_sentiment_history(
    country: Optional[str] = Query(None, description="Filter by ISO-2 country code"),
    topic: Optional[str] = Query(None, description="Filter by GMSI topic name"),
    sentiment_type: Optional[str] = Query("directional", description="directional or semantic_sentiment"),
    index_type: Optional[str] = Query("COMBINED", description="COMBINED, DOMESTIC, or INTERNATIONAL"),
    hours: int = Query(168, ge=1, le=2160, description="Lookback window in hours (default 7 days)"),
):
    """
    Return the full hourly sentiment time series.

    Both sentiment_avg and activity_weighted are included so callers can plot
    and compare the mean-per-headline and volume-adjusted signals.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        with get_db() as conn:
            query = "SELECT * FROM gmsi_index WHERE publication_time >= ?"
            params: list = [since]
            if country:
                query += " AND country = ?"
                params.append(country)
            if topic:
                query += " AND topic = ?"
                params.append(topic)
            if sentiment_type:
                query += " AND sentiment_type = ?"
                params.append(sentiment_type)
            if index_type:
                query += " AND index_type = ?"
                params.append(index_type)
            df = pd.read_sql(query, conn, params=params)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc

    if df.empty:
        return []

    agg = compute_sentiment_indicator(df)

    return [
        SentimentPoint(
            country=str(row.country),
            topic=str(row.topic),
            sentiment_type=str(row.sentiment_type),
            index_type=str(row.index_type),
            publication_time=row.publication_time,
            sentiment_avg=round(float(row.sentiment_avg), 4),
            sentiment_smooth=round(float(row.sentiment_smooth), 4),
            activity_weighted=round(float(row.activity_weighted), 4),
            headline_count=int(row.headline_count),
            indicator=row.indicator,
        )
        for row in agg.itertuples()
    ]
