import logging
import time
from datetime import datetime, timezone

import requests

from backfill import backfill
from config import settings, INDEX_TYPES
from db import setup_database, upsert_regional
from fetcher import fetch_live_regional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def poll_once() -> None:
    """Fetch live regional macro sentiment for all index types and upsert into the database."""
    total_fetched = total_upserted = 0
    for index_type in INDEX_TYPES:
        try:
            records = fetch_live_regional(index_type)
            n = upsert_regional(records)
            total_fetched += len(records)
            total_upserted += n
            logger.info(
                "  %-15s %4d fetched | %4d upserted",
                index_type, len(records), n,
            )
        except requests.HTTPError as e:
            logger.error(
                "  %-15s HTTP %s — skipping, will retry next poll",
                index_type, e.response.status_code,
            )
        except Exception:
            logger.exception("  %s: unexpected error during poll", index_type)
    logger.info(
        "  ── total: %4d fetched | %4d upserted",
        total_fetched, total_upserted,
    )


def main() -> None:
    logger.info("=" * 60)
    logger.info("Permutable AI  |  Regional Macro Sentiment Poller")
    logger.info("=" * 60)
    logger.info("Model ID       : %s", settings.model_id)
    logger.info("Country preset : %s", settings.country_preset)
    logger.info("Index types    : %s", ", ".join(INDEX_TYPES))
    logger.info("Poll interval  : %ds (%d min)", settings.poll_interval_seconds, settings.poll_interval_seconds // 60)
    logger.info("Backfill days  : %d", settings.backfill_days)
    logger.info("Database       : %s", settings.db_path)
    logger.info("=" * 60)

    setup_database()
    logger.info("Database schema ready.")

    backfill()

    poll_count = 0
    logger.info("Entering live polling loop...")

    while True:
        poll_count += 1
        t_start = datetime.now(timezone.utc)
        logger.info("[Poll %d]  %s", poll_count, t_start.strftime("%Y-%m-%d %H:%M:%S UTC"))

        poll_once()

        elapsed = (datetime.now(timezone.utc) - t_start).total_seconds()
        wait = max(0.0, settings.poll_interval_seconds - elapsed)
        logger.info(
            "  Completed in %.1fs.  Next poll in %.1f min.",
            elapsed, wait / 60,
        )
        time.sleep(wait)


if __name__ == "__main__":
    main()
