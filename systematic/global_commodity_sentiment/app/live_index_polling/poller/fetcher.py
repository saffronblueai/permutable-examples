import logging
import random
import time
from datetime import date, datetime, timezone

import requests
from config import settings

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({"x-api-key": settings.api_key, "accept": "application/json"})


def _get(path: str, params: dict, max_retries: int = 5):
    """
    GET a Permutable API path.

    Retries 429 and 5xx responses with exponential backoff plus jitter. Every
    request counts against the monthly quota, so retries are capped.
    """
    params = {k: v for k, v in params.items() if v is not None}
    delay = 1.0
    for attempt in range(max_retries + 1):
        response = _session.get(f"{settings.base_url}{path}", params=params, timeout=60)
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == max_retries:
                response.raise_for_status()
            wait = delay + random.uniform(0, delay / 2)
            logger.warning("    HTTP %s, retrying in %.1fs", response.status_code, wait)
            time.sleep(wait)
            delay *= 2
            continue
        response.raise_for_status()
        return response.json()


def _stamp(records: list[dict], ticker: str, index_type: str, sentiment_type: str) -> list[dict]:
    """
    Normalise records in place.

    The index row does not repeat the requested index type or horizon, so both
    are written from the request. processed_at is stored as an ISO UTC string
    so string comparisons in SQLite order correctly.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    for record in records:
        record["ticker"] = record.get("ticker") or ticker
        record["index_type"] = index_type
        record["sentiment_type"] = sentiment_type
        extracted = datetime.fromisoformat(str(record["processed_at"]).replace("Z", "+00:00"))
        if extracted.tzinfo is None:
            extracted = extracted.replace(tzinfo=timezone.utc)
        record["processed_at"] = extracted.astimezone(timezone.utc).isoformat()
        record["fetched_at"] = fetched_at
    return records


def _params(ticker: str, index_type: str, sentiment_type: str) -> dict:
    # One ticker per call. topic_preset=ALL stays under the 1000-row live cap;
    # a sector or ALL ticker preset can be cut off silently.
    return {
        "ticker_preset": ticker,
        "topic_preset": "ALL",
        "index_type": index_type,
        "sentiment_type": sentiment_type,
        "limit": settings.page_limit,
    }


def fetch_live_index(ticker: str, index_type: str, sentiment_type: str) -> list[dict]:
    """
    Fetch the most recent hourly GCSI index bars for one ticker, index type and horizon.

    The live route returns a plain list for the last 24 hours. The newest bars
    can still be revised as late headlines arrive, so callers must upsert.
    """
    body = _get(settings.index_live_path, _params(ticker, index_type, sentiment_type))
    records = body if isinstance(body, list) else body["data"]
    return _stamp(records, ticker, index_type, sentiment_type)


def fetch_historical_index(
    ticker: str,
    index_type: str,
    sentiment_type: str,
    start_date: date,
    end_date: date | None = None,
) -> list[dict]:
    """
    Page through the historical GCSI index with keyset pagination.

    Each response carries 'data', 'has_more' and 'next_token'. Loop until has_more is False.
    start_date is required. The route covers at most 90 days.
    """
    params = _params(ticker, index_type, sentiment_type)
    params.update(
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat() if end_date else None,
        }
    )
    records: list[dict] = []
    page = 1
    while True:
        body = _get(settings.index_historical_path, params)
        records.extend(body["data"])
        logger.info("      page %3d: %5d records | total %6d", page, len(body["data"]), len(records))
        if not body.get("has_more"):
            break
        params["next_token"] = body["next_token"]
        page += 1
    return _stamp(records, ticker, index_type, sentiment_type)
