import logging
from datetime import date, datetime, timezone

import requests

from config import settings

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {"x-api-key": settings.api_key}


def _enrich(records: list[dict]) -> None:
    """Flatten countries list and stamp fetched_at in-place."""
    ts = datetime.now(timezone.utc).isoformat()
    for r in records:
        r["countries"] = "|".join(r.get("countries") or [])
        r["fetched_at"] = ts


def fetch_live_headlines(ticker: str) -> list[dict]:
    """
    Fetch live per-headline sentiment for a single ticker.

    Calls GET /v1/headlines/feed/live/ticker/{ticker} and returns a flat list
    of record dicts matching the AssetHeadline schema. The endpoint always
    returns the most recent 2-hour window (up to 1,000 records).
    """
    url = f"{settings.base_url}/headlines/feed/live/ticker/{ticker}"
    params = {
        "match_type"                 : settings.match_type,
        "topic_preset"               : settings.topic_preset,
        "language_preset"            : settings.language_preset,
        "source_preset"              : settings.source_preset,
        "source_country_preset"      : settings.source_country_preset,
        "topic_probability_threshold": settings.topic_probability_threshold,
        "abs_sentiment_threshold"    : settings.abs_sentiment_threshold,
        "limit"                      : 1000,
    }
    response = requests.get(url, params=params, headers=_headers(), timeout=30)
    response.raise_for_status()
    records = response.json()
    _enrich(records)
    return records


def fetch_historical_headlines(
    ticker: str,
    start_date: date,
    end_date: date | None = None,
) -> list[dict]:
    """
    Paginate through GET /v1/headlines/feed/historical/ticker/{ticker}.

    Uses keyset pagination: each response contains 'has_more' and 'next_token'.
    Loops until has_more is False, passing next_token into every subsequent request.
    Supports up to 90 days of lookback.
    """
    url = f"{settings.base_url}/headlines/feed/historical/ticker/{ticker}"
    params: dict = {
        "start_date"                 : start_date.isoformat(),
        "match_type"                 : settings.match_type,
        "topic_preset"               : settings.topic_preset,
        "language_preset"            : settings.language_preset,
        "source_preset"              : settings.source_preset,
        "source_country_preset"      : settings.source_country_preset,
        "topic_probability_threshold": settings.topic_probability_threshold,
        "abs_sentiment_threshold"    : settings.abs_sentiment_threshold,
        "limit"                      : 1000,
    }
    if end_date:
        params["end_date"] = end_date.isoformat()

    all_records: list[dict] = []
    page = 1

    while True:
        response = requests.get(url, params=params, headers=_headers(), timeout=30)
        response.raise_for_status()
        body = response.json()
        records = body["data"]
        _enrich(records)
        all_records.extend(records)
        logger.info(
            "  page %3d: %5d records  |  total so far: %6d",
            page, len(records), len(all_records),
        )
        if not body["has_more"]:
            break
        params["next_token"] = body["next_token"]
        page += 1

    return all_records
