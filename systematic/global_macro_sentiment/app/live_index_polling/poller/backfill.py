import logging
from datetime import date, datetime, timedelta

import requests

from config import settings
from db import latest_publication_date, upsert_index
from fetcher import fetch_historical_index

logger = logging.getLogger(__name__)


def _start_date_for(
    country: str, topic: str, sentiment_type: str, index_type: str, days_back: int,
) -> date:
    """
    Return the date to start fetching historical index data for a given combination.

    Resumes from the latest stored record if data already exists, otherwise falls
    back to now − days_back for a fresh seed.
    """
    latest = latest_publication_date(country, topic, sentiment_type, index_type)
    if latest is not None:
        logger.info("    DB has data up to %s — resuming from there", latest)
        return latest
    fallback = (datetime.utcnow() - timedelta(days=days_back)).date()
    logger.info("    No existing data — full backfill from %s (%d days)", fallback, days_back)
    return fallback


def backfill_all(days_back: int | None = None) -> None:
    """
    Fetch and upsert historical GMSI index records for all configured combinations.

    Runs once on startup before the live polling loop begins. On the first run
    it seeds the database with `days_back` days of history. On subsequent
    container restarts it only fetches the gap from the latest stored record.
    """
    days_back = days_back if days_back is not None else settings.backfill_days
    combos = [
        (c, t, st, it)
        for c in settings.countries_list
        for t in settings.topics_list
        for st in settings.sentiment_types_list
        for it in settings.index_types_list
    ]
    logger.info(
        "Starting backfill for %d combinations (max window: %d days)", len(combos), days_back
    )

    for country, topic, sentiment_type, index_type in combos:
        key = f"{country}/{topic}/{sentiment_type}/{index_type}"
        logger.info("  %s", key)
        try:
            start = _start_date_for(country, topic, sentiment_type, index_type, days_back)
            records = fetch_historical_index(country, topic, sentiment_type, index_type, start)
            n = upsert_index(records)
            logger.info("    %d rows upserted", n)
        except requests.HTTPError as e:
            logger.error("    HTTP %s — skipping combination", e.response.status_code)
        except Exception:
            logger.exception("    Unexpected error for %s", key)

    logger.info("Backfill complete.")
