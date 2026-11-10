import logging
from datetime import date, datetime, timedelta, timezone

import requests
from config import settings
from db import latest_processed_at, upsert_headlines
from fetcher import fetch_historical_feed

logger = logging.getLogger(__name__)


def _start_date_for(ticker: str) -> date:
    """
    Return the date to start fetching headlines for *ticker*.

    - If the DB already has rows, resume from the day of the newest stored row.
    - Otherwise fall back to now − BACKFILL_DAYS for a fresh seed.
    """
    latest = latest_processed_at(ticker)
    if latest is not None:
        logger.info("    DB has data up to %s; resuming from that day", latest.isoformat())
        return latest.date()
    start = (datetime.now(timezone.utc) - timedelta(days=settings.backfill_days)).date()
    logger.info("    No existing data; full backfill from %s (%d days)", start, settings.backfill_days)
    return start


def backfill_all() -> None:
    """
    Fetch and upsert historical GCSI headlines for every configured ticker.

    Runs once on startup before the live polling loop. Both the historical and
    live endpoints write through upsert_headlines(), so data is de-duplicated
    across runs.
    """
    logger.info("Starting backfill for %d tickers (max window: %d days)", len(settings.tickers_list), settings.backfill_days)
    for ticker in settings.tickers_list:
        logger.info("  %s", ticker)
        try:
            start = _start_date_for(ticker)
            n = sum(upsert_headlines(fetch_historical_feed(ticker, start, m)) for m in settings.match_types_list)
            logger.info("    %d rows upserted", n)
        except requests.HTTPError as e:
            logger.error("    HTTP %s; skipping ticker", e.response.status_code)
        except Exception:
            logger.exception("    Unexpected error fetching %s", ticker)
    logger.info("Backfill complete.")
