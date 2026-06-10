import logging
from datetime import date, datetime, timezone

import requests

from config import settings

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {"x-api-key": settings.api_key}


def _stamp(records: list[dict], country: str, topic: str, match_type: str) -> None:
    """Attach request context and fetch timestamp in-place.

    The GMSI raw feed omits country, topic, and match_type from each JSON
    record — they must be carried from the request parameters.
    """
    ts = datetime.now(timezone.utc).isoformat()
    for r in records:
        r["country"] = country
        r["topic"] = topic
        r["match_type"] = match_type
        r["fetched_at"] = ts


def fetch_live_headlines(country: str, topic: str, match_type: str) -> list[dict]:
    """
    Fetch the live GMSI raw headline feed for one country/topic/match_type.

    Calls GET /v1/headlines/feed/live/gmsi/{country} and returns a flat list
    of record dicts. The live window covers the most recent headlines (up to
    1 000 records). Country/topic/match_type are stamped in by _stamp().
    """
    url = f"{settings.base_url}/headlines/feed/live/gmsi/{country}"
    response = requests.get(
        url,
        params={"topic": topic, "match_type": match_type, "limit": 1000},
        headers=_headers(),
        timeout=30,
    )
    response.raise_for_status()
    records = response.json()
    _stamp(records, country, topic, match_type)
    return records


def fetch_historical_headlines(
    country: str,
    topic: str,
    match_type: str,
    start_date: date,
    end_date: date | None = None,
) -> list[dict]:
    """
    Paginate through GET /v1/headlines/feed/historical/gmsi/{country}.

    Uses keyset pagination: each response envelope has 'has_more' and
    'next_token'. Loops until has_more is False. Supports up to 90 days
    of lookback.
    """
    url = f"{settings.base_url}/headlines/feed/historical/gmsi/{country}"
    params: dict = {
        "topic": topic,
        "match_type": match_type,
        "start_date": start_date.isoformat(),
        "limit": 1000,
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
        _stamp(records, country, topic, match_type)
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
