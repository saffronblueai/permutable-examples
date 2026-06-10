import logging
from datetime import date, datetime, timedelta

import requests

from config import settings
from db import latest_publication_date, upsert_headlines
from fetcher import fetch_historical_headlines

logger = logging.getLogger(__name__)


def _start_date_for(country: str, topic: str, match_type: str, days_back: int) -> date:
    """
    Return the date to start fetching historical data for a given combination.

    - If the DB already has rows for this key, resume from the date of the
      latest stored record so we only fetch the gap, not the full window.
    - Otherwise fall back to now − days_back for a fresh seed.
    """
    latest = latest_publication_date(country, topic, match_type)
    if latest is not None:
        logger.info("    DB has data up to %s — resuming from there", latest)
        return latest
    fallback = (datetime.utcnow() - timedelta(days=days_back)).date()
    logger.info("    No existing data — full backfill from %s (%d days)", fallback, days_back)
    return fallback


def backfill_all(days_back: int | None = None) -> None:
    """
    Fetch and upsert historical GMSI headlines for all configured combinations.

    Runs once on startup before the live polling loop begins. On the first run
    it seeds the database with `days_back` days of history. On subsequent
    container restarts it only fetches the gap from the latest stored record.
    """
    days_back = days_back if days_back is not None else settings.backfill_days
    combos = [
        (c, t, settings.match_type)
        for c in settings.countries_list
        for t in settings.topics_list
    ]
    logger.info("Starting backfill for %d combinations (max window: %d days)", len(combos), days_back)

    for country, topic, match_type in combos:
        logger.info("  %s / %s / %s", country, topic, match_type)
        try:
            start = _start_date_for(country, topic, match_type, days_back)
            records = fetch_historical_headlines(country, topic, match_type, start)
            n = upsert_headlines(records)
            logger.info("    %d rows upserted", n)
        except requests.HTTPError as e:
            logger.error("    HTTP %s — skipping combination", e.response.status_code)
        except Exception:
            logger.exception("    Unexpected error for %s / %s", country, topic)

    logger.info("Backfill complete.")
