import logging
from datetime import datetime, timedelta, date

import requests

from config import settings
from db import latest_publication_date, upsert_index
from fetcher import fetch_historical_index

logger = logging.getLogger(__name__)


def _start_date_for(ticker: str, days_back: int) -> date:
    """
    Return the date to start fetching historical index data for *ticker*.

    - If the DB already has rows for this ticker, resume from the date of the
      latest stored record so we only fetch the gap, not the full window.
    - Otherwise fall back to now − days_back for a fresh seed.
    """
    latest = latest_publication_date(ticker)
    if latest is not None:
        logger.info("    DB has data up to %s — resuming from there", latest)
        return latest
    fallback = (datetime.utcnow() - timedelta(days=days_back)).date()
    logger.info("    No existing data — full backfill from %s (%d days)", fallback, days_back)
    return fallback


def backfill_all_tickers(days_back: int | None = None) -> None:
    """
    Fetch and upsert historical headline index for all configured tickers.

    Runs once on startup before the live polling loop begins. On the first run
    it seeds the database with `days_back` days of history. On subsequent
    container restarts it only fetches the gap between the latest stored record
    and now, avoiding redundant API calls and re-processing of already-stored data.

    Both the historical and live endpoints write via upsert_index() so data
    is automatically de-duplicated across runs.
    """
    days_back = days_back if days_back is not None else settings.backfill_days

    logger.info("Starting backfill for %d tickers (max window: %d days)", len(settings.tickers_list), days_back)

    for ticker in settings.tickers_list:
        logger.info("  %s", ticker)
        try:
            start = _start_date_for(ticker, days_back)
            records = fetch_historical_index(ticker, start)
            n = upsert_index(records)
            logger.info("    %d rows upserted", n)
        except requests.HTTPError as e:
            logger.error("    HTTP %s — skipping ticker", e.response.status_code)
        except Exception:
            logger.exception("    Unexpected error fetching %s", ticker)

    logger.info("Backfill complete.")
