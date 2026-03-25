import logging
import time
from datetime import datetime, timezone

import requests

from backfill import backfill_all_tickers
from config import settings
from db import setup_database, upsert_index
from fetcher import fetch_live_index

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def poll_once() -> None:
    """Fetch live headline index for all configured tickers and upsert into the database."""
    for ticker in settings.tickers_list:
        try:
            records = fetch_live_index(ticker)
            n = upsert_index(records)
            logger.info("  %-12s: %4d fetched | %4d upserted", ticker, len(records), n)
        except requests.HTTPError as e:
            logger.error(
                "  %s: HTTP %s — skipping, will retry next poll",
                ticker, e.response.status_code,
            )
        except Exception:
            logger.exception("  %s: unexpected error", ticker)


def main() -> None:
    logger.info("=" * 60)
    logger.info("Permutable AI  |  Headline Index Poller")
    logger.info("=" * 60)
    logger.info("Tickers        : %s", settings.tickers_list)
    logger.info("Index type     : %s", settings.index_type)
    logger.info("Poll interval  : %ds (%d min)", settings.poll_interval_seconds, settings.poll_interval_seconds // 60)
    logger.info("Backfill days  : %d", settings.backfill_days)
    logger.info("Database       : %s", settings.db_path)
    logger.info("=" * 60)

    setup_database()
    logger.info("Database schema ready.")

    backfill_all_tickers()

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
