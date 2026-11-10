import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from config import settings
from db import get_db
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from models import BinPoint, EntityTypeCount, Headline, HealthResponse, MatchTypeSummary, TopicSentiment
from signals import HORIZON_COLUMNS, binned_series, entity_type_summary, match_type_summary, topic_summary

app = FastAPI(
    title="Permutable AI  |  GCSI Headline Feed API",
    description=(
        "Local API exposing Global Commodity Sentiment Indices (GCSI) headlines and "
        "your own aggregations of them. All data is read from the local SQLite "
        "database, which the poller service keeps up to date. Headline text belongs "
        "to its publishers; use it under your Permutable licence."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

HORIZON = Query("short_term", description="short_term | medium_term | long_term")


def _load(hours: int, ticker: Optional[str] = None, match_type: Optional[str] = None) -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query = "SELECT * FROM gcsi_headlines WHERE processed_at >= ? AND topic_probability >= ?"
    params: list = [since, settings.min_topic_probability]
    if ticker:
        query += " AND ticker = ?"
        params.append(ticker)
    if match_type:
        query += " AND match_type = ?"
        params.append(match_type)
    try:
        with get_db() as conn:
            return pd.read_sql(query, conn, params=params)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc


def _check(horizon: str) -> None:
    if horizon not in HORIZON_COLUMNS:
        raise HTTPException(status_code=422, detail=f"horizon must be one of {list(HORIZON_COLUMNS)}")


def _clean(value: float) -> float | None:
    return None if math.isnan(value) else round(value, 4)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Monitoring"])
def health():
    """Returns service status, the row count and the newest processed time."""
    try:
        with get_db() as conn:
            count, latest = conn.execute("SELECT COUNT(*), MAX(processed_at) FROM gcsi_headlines").fetchone()
        return HealthResponse(status="ok", db_path=settings.db_path, row_count=count, latest_processed_at=latest)
    except Exception:
        return HealthResponse(status="ok", db_path=settings.db_path)


# ── Headlines ──────────────────────────────────────────────────────────────────

@app.get("/headlines", response_model=list[Headline], tags=["Data"])
def get_headlines(
    ticker: Optional[str] = Query(None, description="Filter by ticker"),
    match_type: Optional[str] = Query(None, description="EXPLICIT | RELATED_ENTITY | MACROECONOMIC"),
    hours: int = Query(6, ge=1, le=720, description="Lookback window in hours"),
    sort: str = Query("recent", description="recent | strongest (largest absolute short-term score)"),
    limit: int = Query(50, ge=1, le=5000, description="Max rows to return"),
):
    """Recent headlines, newest first or strongest first. One row per headline × topic."""
    df = _load(hours, ticker, match_type)
    if df.empty:
        return []
    if sort == "strongest":
        df = df.reindex(df["short_term_sentiment_score"].abs().sort_values(ascending=False).index)
        df = df.drop_duplicates(subset=["ticker", "link"])
    else:
        df = df.sort_values("processed_at", ascending=False)
    top = df.head(limit)
    return top.astype(object).where(top.notna(), None).to_dict("records")


# ── Aggregations ───────────────────────────────────────────────────────────────

@app.get("/sentiment/bins", response_model=list[BinPoint], tags=["Sentiment"])
def get_bins(
    ticker: Optional[str] = Query(None, description="Filter by ticker"),
    match_type: Optional[str] = Query(None, description="Filter by match type"),
    horizon: str = HORIZON,
    hours: int = Query(48, ge=1, le=720, description="Lookback window in hours"),
):
    """Own index from the headline feed: BIN_MINUTES bins on processed time, smoothed over SMOOTHING_HOURS."""
    _check(horizon)
    series = binned_series(_load(hours, ticker, match_type), horizon)
    return [
        BinPoint(
            ticker=r.ticker, match_type=r.match_type, bin_end=r.bin_end, headline_count=int(r.headline_count),
            sentiment_avg=round(float(r.sentiment_avg), 4), sentiment_std=round(float(r.sentiment_std), 4),
            sentiment_smooth=_clean(float(r.sentiment_smooth)), window_count=int(r.window_count),
        )
        for r in series.itertuples()
    ]


@app.get("/topics", response_model=list[TopicSentiment], tags=["Sentiment"])
def get_topics(
    ticker: Optional[str] = Query(None, description="Filter by ticker"),
    horizon: str = HORIZON,
    hours: int = Query(48, ge=1, le=720, description="Lookback window in hours"),
    limit: int = Query(15, ge=1, le=200, description="Number of topics, busiest first"),
):
    """Average score per topic over the window, busiest topics first."""
    _check(horizon)
    summary = topic_summary(_load(hours, ticker), horizon).head(limit)
    return [
        TopicSentiment(topic=r.topic, headline_count=int(r.headline_count), sentiment_avg=round(float(r.sentiment_avg), 4))
        for r in summary.itertuples()
    ]


@app.get("/match-types", response_model=list[MatchTypeSummary], tags=["Sentiment"])
def get_match_types(
    ticker: Optional[str] = Query(None, description="Filter by ticker"),
    hours: int = Query(48, ge=1, le=720, description="Lookback window in hours"),
):
    """Rows, distinct articles and average score per horizon for each match type."""
    summary = match_type_summary(_load(hours, ticker))
    return [
        MatchTypeSummary(
            match_type=r.match_type, rows=int(r.rows), articles=int(r.articles),
            avg_short_term=_clean(float(r.avg_short_term)), avg_medium_term=_clean(float(r.avg_medium_term)),
            avg_long_term=_clean(float(r.avg_long_term)),
        )
        for r in summary.itertuples()
    ]


@app.get("/entity-types", response_model=list[EntityTypeCount], tags=["Sentiment"])
def get_entity_types(
    ticker: Optional[str] = Query(None, description="Filter by ticker"),
    hours: int = Query(48, ge=1, le=720, description="Lookback window in hours"),
    limit: int = Query(15, ge=1, le=100, description="Number of entity types, most articles first"),
):
    """Distinct articles per matched entity type: what linked the news to the commodity."""
    summary = entity_type_summary(_load(hours, ticker)).head(limit)
    return [
        EntityTypeCount(entity_type=r.entity_type, family=r.family, articles=int(r.articles))
        for r in summary.itertuples()
    ]
