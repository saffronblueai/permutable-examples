from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db import get_db
from models import CountrySignal, GmsiHeadline, HealthResponse, SignalPoint
from signals import compute_signals

app = FastAPI(
    title="Permutable AI  |  GMSI Headline API",
    description=(
        "Internal API exposing live GMSI raw headline data and computed signals "
        "derived from the Permutable AI Global Macro Sentiment Indices feed. "
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
            count = conn.execute("SELECT COUNT(*) FROM gmsi_headlines").fetchone()[0]
        return HealthResponse(status="ok", db_path=settings.db_path, row_count=count)
    except Exception:
        return HealthResponse(status="ok", db_path=settings.db_path)


# ── Raw headlines ───────────────────────────────────────────────────────────────


@app.get("/headlines", response_model=list[GmsiHeadline], tags=["Data"])
def get_headlines(
    country: Optional[str] = Query(None, description="Filter by ISO-2 country code"),
    topic: Optional[str] = Query(None, description="Filter by GMSI topic name"),
    hours: int = Query(24, ge=1, le=2160, description="Lookback window in hours"),
    limit: int = Query(5000, ge=1, le=50000, description="Max rows to return"),
):
    """
    Return recent GMSI headlines from the database.

    Each row represents a single headline scored by both the directional and
    semantic sentiment models. By default returns the last 24 hours across all
    countries and topics.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        with get_db() as conn:
            query = "SELECT * FROM gmsi_headlines WHERE publication_time >= ?"
            params: list = [since]
            if country:
                query += " AND country = ?"
                params.append(country)
            if topic:
                query += " AND topic = ?"
                params.append(topic)
            query += " ORDER BY publication_time DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc

    return [dict(r) for r in rows]


# ── Signals ─────────────────────────────────────────────────────────────────────


@app.get("/signals/latest", response_model=list[CountrySignal], tags=["Signals"])
def get_latest_signals(
    hours: int = Query(4, ge=1, le=48, description="Lookback window for signal computation"),
):
    """
    Return the latest directional signal for every (country, topic) in the database.

    Signal is derived from a 15-min binned rolling mean of directional_score,
    thresholded to HIGH / NEUTRAL / LOW.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        with get_db() as conn:
            df = pd.read_sql(
                "SELECT * FROM gmsi_headlines WHERE publication_time >= ?",
                conn,
                params=(since,),
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc

    if df.empty:
        return []

    signals = compute_signals(df)
    now = datetime.now(timezone.utc)
    result = []

    for (country, topic), grp in signals.groupby(["country", "topic"]):
        last = grp.sort_values("publication_time").iloc[-1]
        result.append(
            CountrySignal(
                country=str(country),
                topic=str(topic),
                publication_time=last["publication_time"],
                directional_mean=round(float(last["directional_mean"]), 4),
                semantic_mean=round(float(last["semantic_mean"]), 4),
                directional_smooth=round(float(last["directional_smooth"]), 4),
                semantic_smooth=round(float(last["semantic_smooth"]), 4),
                headline_count=int(last["headline_count"]),
                signal=last["signal"],
                computed_at=now,
            )
        )

    return sorted(result, key=lambda s: (s.country, s.topic))


@app.get("/signals/history", response_model=list[SignalPoint], tags=["Signals"])
def get_signal_history(
    country: Optional[str] = Query(None, description="Filter by ISO-2 country code"),
    topic: Optional[str] = Query(None, description="Filter by GMSI topic name"),
    hours: int = Query(24, ge=1, le=2160, description="Lookback window in hours"),
):
    """
    Return the full 15-min signal time series for one or all country/topic combinations.

    Suitable for chart rendering. Both directional and semantic smoothed series
    are included so callers can plot and compare them.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        with get_db() as conn:
            query = "SELECT * FROM gmsi_headlines WHERE publication_time >= ?"
            params: list = [since]
            if country:
                query += " AND country = ?"
                params.append(country)
            if topic:
                query += " AND topic = ?"
                params.append(topic)
            df = pd.read_sql(query, conn, params=params)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc

    if df.empty:
        return []

    signals = compute_signals(df)

    return [
        SignalPoint(
            country=str(row.country),
            topic=str(row.topic),
            publication_time=row.publication_time,
            directional_mean=round(float(row.directional_mean), 4),
            semantic_mean=round(float(row.semantic_mean), 4),
            directional_smooth=round(float(row.directional_smooth), 4),
            semantic_smooth=round(float(row.semantic_smooth), 4),
            headline_count=int(row.headline_count),
            signal=row.signal,
        )
        for row in signals.itertuples()
    ]
