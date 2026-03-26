import logging
from datetime import datetime, timedelta, date

import requests

from config import settings, INDEX_TYPES
from db import latest_publication_date, upsert_regional
from fetcher import fetch_historical_regional

logger = logging.getLogger(__name__)


def _start_date(index_type: str, days_back: int) -> date:
    """
    Return the start date for the historical backfill of a given index_type.

    Resumes from the latest stored record date if one exists, otherwise falls
    back to now − days_back for a fresh seed.
    """
    latest = latest_publication_date(index_type)
    if latest is not None:
        logger.info("    DB has data up to %s — resuming from there", latest)
        return latest
    fallback = (datetime.utcnow() - timedelta(days=days_back)).date()
    logger.info("    No existing data — full backfill from %s (%d days)", fallback, days_back)
    return fallback


def backfill(days_back: int | None = None) -> None:
    """
    Fetch and upsert historical regional macro sentiment for all index types.

    Runs once on startup before the live polling loop begins. Each index type
    is backfilled independently so that DOMESTIC and INTERNATIONAL gaps are
    filled correctly even if COMBINED data already exists.
    """
    days_back = days_back if days_back is not None else settings.backfill_days
    logger.info(
        "Starting backfill for model %s / country_preset %s",
        settings.model_id, settings.country_preset,
    )
    for index_type in INDEX_TYPES:
        logger.info("  [%s]", index_type)
        start = _start_date(index_type, days_back)
        try:
            records = fetch_historical_regional(start, index_type=index_type)
            n = upsert_regional(records)
            logger.info("    %d rows upserted", n)
        except requests.HTTPError as e:
            logger.error("    HTTP %s — skipping backfill for %s", e.response.status_code, index_type)
        except Exception:
            logger.exception("    Unexpected error during backfill for %s", index_type)
    logger.info("Backfill complete.")
