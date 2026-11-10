import logging
from datetime import date, datetime, timedelta, timezone

import requests
from config import settings
from db import latest_processed_at, upsert_index
from fetcher import fetch_historical_index

logger = logging.getLogger(__name__)


def _start_date_for(ticker: str, index_type: str, sentiment_type: str) -> date:
    """
    Return the date to start fetching history for one series.

    - If the DB already has rows, resume a few hours before the newest stored
      bar (REVISION_HOURS) so bars revised while the poller was down are refreshed.
    - Otherwise fall back to now − BACKFILL_DAYS for a fresh seed.
    """
    latest = latest_processed_at(ticker, index_type, sentiment_type)
    if latest is not None:
        start = (latest - timedelta(hours=settings.revision_hours)).date()
        logger.info("    DB has data up to %s; resuming from %s", latest.isoformat(), start)
        return start
    start = (datetime.now(timezone.utc) - timedelta(days=settings.backfill_days)).date()
    logger.info("    No existing data; full backfill from %s (%d days)", start, settings.backfill_days)
    return start


def backfill_all() -> None:
    """
    Fetch and upsert historical GCSI index data for every configured series.

    Runs once on startup before the live polling loop. Both the historical and
    live endpoints write through upsert_index(), so data is de-duplicated
    across runs.
    """
    logger.info("Starting backfill (max window: %d days)", settings.backfill_days)
    for ticker in settings.tickers_list:
        for index_type in settings.index_types_list:
            for sentiment_type in settings.sentiment_types_list:
                logger.info("  %s / %s / %s", ticker, index_type, sentiment_type)
                try:
                    start = _start_date_for(ticker, index_type, sentiment_type)
                    n = upsert_index(fetch_historical_index(ticker, index_type, sentiment_type, start))
                    logger.info("    %d rows upserted", n)
                except requests.HTTPError as e:
                    logger.error("    HTTP %s; skipping this series", e.response.status_code)
                except Exception:
                    logger.exception("    Unexpected error")
    logger.info("Backfill complete.")
