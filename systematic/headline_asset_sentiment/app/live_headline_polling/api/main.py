from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db import get_db
from models import HealthResponse, Headline, SignalPoint, TickerSignal
from signals import compute_signals

app = FastAPI(
    title="Permutable AI  |  Headline Sentiment API",
    description=(
        "Internal API exposing live headline sentiment data and computed signals "
        "derived from the Permutable AI headline feed. All data is sourced from the "
        "local SQLite database, which is continuously populated by the poller service."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Monitoring"])
def health():
    """Returns service status and the current row count in the database."""
    try:
        with get_db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM headline_sentiment").fetchone()[0]
        return HealthResponse(status="ok", db_path=settings.db_path, row_count=count)
    except Exception:
        # DB not yet created by the poller — return healthy with no count
        return HealthResponse(status="ok", db_path=settings.db_path)


# ── Raw headlines ──────────────────────────────────────────────────────────────

@app.get("/headlines", response_model=list[Headline], tags=["Data"])
def get_headlines(
    ticker: Optional[str] = Query(None, description="Filter by ticker symbol"),
    hours: int = Query(24, ge=1, le=2160, description="Lookback window in hours"),
    limit: int = Query(1000, ge=1, le=10000, description="Max rows to return"),
):
    """
    Return recent headlines from the database.

    By default returns the last 24 hours across all tickers. Use `ticker` to
    scope to a single asset and `hours` to widen the lookback window.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        with get_db() as conn:
            query = "SELECT * FROM headline_sentiment WHERE publication_time >= ?"
            params: list = [since]
            if ticker:
                query += " AND ticker = ?"
                params.append(ticker)
            query += " ORDER BY publication_time DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc

    return [dict(r) for r in rows]


# ── Signals ────────────────────────────────────────────────────────────────────

@app.get("/signals/latest", response_model=list[TickerSignal], tags=["Signals"])
def get_latest_signals(
    hours: int = Query(4, ge=1, le=48, description="Lookback window for signal computation"),
):
    """
    Return the latest LONG / SHORT / FLAT signal for every ticker present in the database.

    Signal computation mirrors the notebook strategy exactly:
    - 15-min bins → 2-period rolling mean of sentiment_mean → threshold at ±BULLISH_THRESHOLD.
    - The most recent bin per ticker is returned.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        with get_db() as conn:
            df = pd.read_sql(
                "SELECT * FROM headline_sentiment WHERE publication_time >= ?",
                conn, params=(since,),
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc

    if df.empty:
        return []

    signals = compute_signals(df)
    now = datetime.now(timezone.utc)
    result = []

    for ticker, grp in signals.groupby("ticker"):
        last = grp.sort_values("publication_time").iloc[-1]
        result.append(
            TickerSignal(
                ticker=str(ticker),
                publication_time=last["publication_time"],
                sentiment_mean=round(float(last["sentiment_mean"]), 4),
                conviction=round(float(last["conviction"]), 4),
                headline_count=int(last["headline_count"]),
                signal_smooth=round(float(last["signal_smooth"]), 4),
                signal=last["signal"],
                computed_at=now,
            )
        )

    return sorted(result, key=lambda s: s.ticker)


@app.get("/signals/history", response_model=list[SignalPoint], tags=["Signals"])
def get_signal_history(
    ticker: Optional[str] = Query(None, description="Filter by ticker symbol"),
    hours: int = Query(24, ge=1, le=2160, description="Lookback window in hours"),
):
    """
    Return the full 15-min signal time series for one or all tickers.

    Suitable for chart rendering. Use `hours` to control the chart window —
    e.g. `hours=168` for 7 days of historical data.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        with get_db() as conn:
            query = "SELECT * FROM headline_sentiment WHERE publication_time >= ?"
            params: list = [since]
            if ticker:
                query += " AND ticker = ?"
                params.append(ticker)
            df = pd.read_sql(query, conn, params=params)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not yet available") from exc

    if df.empty:
        return []

    signals = compute_signals(df)

    return [
        SignalPoint(
            ticker=str(row.ticker),
            publication_time=row.publication_time,
            sentiment_mean=round(float(row.sentiment_mean), 4),
            signal_smooth=round(float(row.signal_smooth), 4),
            signal=row.signal,
            headline_count=int(row.headline_count),
        )
        for row in signals.itertuples()
    ]
