import logging
import time
from datetime import datetime, timezone

import requests
from backfill import backfill_all
from config import settings
from db import setup_database, upsert_headlines
from fetcher import fetch_live_feed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def poll_once() -> None:
    """Fetch the live GCSI headline feed for every configured ticker and upsert it into the database."""
    for ticker in settings.tickers_list:
        for match_type in settings.match_types_list:
            label = ticker + (f"/{match_type}" if match_type else "")
            try:
                records = fetch_live_feed(ticker, match_type)
                n = upsert_headlines(records)
                logger.info("  %-30s: %4d fetched | %4d upserted", label, len(records), n)
            except requests.HTTPError as e:
                logger.error("  %s: HTTP %s; skipping, will retry next poll", label, e.response.status_code)
            except Exception:
                logger.exception("  %s: unexpected error", label)


def main() -> None:
    logger.info("=" * 60)
    logger.info("Permutable AI  |  GCSI Headline Feed Poller")
    logger.info("=" * 60)
    logger.info("Tickers        : %s", settings.tickers_list)
    logger.info("Match types    : %s", [m or "ALL" for m in settings.match_types_list])
    logger.info("Poll interval  : %ds (%d min)", settings.poll_interval_seconds, settings.poll_interval_seconds // 60)
    logger.info("Backfill days  : %d", settings.backfill_days)
    logger.info("Database       : %s", settings.db_path)
    logger.info("=" * 60)

    setup_database()
    logger.info("Database schema ready.")

    backfill_all()

    poll_count = 0
    logger.info("Entering live polling loop...")
    while True:
        poll_count += 1
        t_start = datetime.now(timezone.utc)
        logger.info("[Poll %d]  %s", poll_count, t_start.strftime("%Y-%m-%d %H:%M:%S UTC"))

        poll_once()

        elapsed = (datetime.now(timezone.utc) - t_start).total_seconds()
        wait = max(0.0, settings.poll_interval_seconds - elapsed)
        logger.info("  Completed in %.1fs.  Next poll in %.1f min.", elapsed, wait / 60)
        time.sleep(wait)


if __name__ == "__main__":
    main()
