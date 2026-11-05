import hashlib
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


def _utc_iso(value) -> str | None:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _stamp(records: list[dict], ticker: str) -> list[dict]:
    """
    Normalise records in place.

    The feed has no row id, so each row gets a key built from (ticker, topic,
    match type, link or headline, extraction time); polling the same window
    twice is then harmless. Timestamps are stored as ISO UTC strings.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    for record in records:
        record.setdefault("ticker", ticker)
        record["extraction_time"] = _utc_iso(record.get("extraction_time"))
        parts = [record.get(k) or "" for k in ("ticker", "topic", "match_type", "extraction_time")]
        parts.append(record.get("link") or record.get("headline") or "")
        record["row_key"] = hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()
        record["fetched_at"] = fetched_at
    return records


def _params(ticker: str, match_type: str | None) -> dict:
    return {"ticker_preset": ticker, "match_type": match_type, "limit": settings.page_limit}


def fetch_live_feed(ticker: str, match_type: str | None = None) -> list[dict]:
    """Fetch the most recent GCSI headlines for one ticker. The live route returns a plain list."""
    body = _get(settings.feed_live_path, _params(ticker, match_type))
    return _stamp(body if isinstance(body, list) else body["data"], ticker)


def fetch_historical_feed(ticker: str, start_date: date, match_type: str | None = None) -> list[dict]:
    """
    Page through the historical GCSI headline feed with keyset pagination.

    Each response carries 'data', 'has_more' and 'next_token'. Loop until has_more is False.
    start_date is required. The route covers at most 90 days.
    """
    params = _params(ticker, match_type)
    params["start_date"] = start_date.isoformat()
    path = settings.feed_historical_path
    records: list[dict] = []
    page = 1
    while True:
        body = _get(path, params)
        records.extend(body["data"])
        logger.info("      page %3d: %5d records | total %6d", page, len(body["data"]), len(records))
        if not body.get("has_more"):
            break
        params["next_token"] = body["next_token"]
        page += 1
    return _stamp(records, ticker)
