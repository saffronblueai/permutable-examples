import logging
from datetime import date, datetime, timezone

import requests

from config import settings

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {"x-api-key": settings.api_key}


def _stamp(
    records: list[dict],
    country: str,
    topic: str,
    sentiment_type: str,
    index_type: str,
) -> None:
    """Attach request context and fetch timestamp in-place.

    The GMSI hourly index endpoint omits country, topic, sentiment_type, and
    index_type from each JSON record — they must be carried from request params.
    """
    ts = datetime.now(timezone.utc).isoformat()
    for r in records:
        r["country"] = country
        r["topic"] = topic
        r["sentiment_type"] = sentiment_type
        r["index_type"] = index_type
        r["fetched_at"] = ts


def fetch_live_index(
    country: str,
    topic: str,
    sentiment_type: str,
    index_type: str,
) -> list[dict]:
    """
    Fetch the live GMSI hourly index for one country/topic/sentiment_type/index_type.

    Calls GET /v1/headlines/index/gmsi/live/{country} and returns a flat list
    of record dicts. The live window covers the most recent 24 hours.
    """
    url = f"{settings.base_url}/headlines/index/gmsi/live/{country}"
    response = requests.get(
        url,
        params={
            "topic": topic,
            "sentiment_type": sentiment_type,
            "index_type": index_type,
            "limit": 1000,
        },
        headers=_headers(),
        timeout=30,
    )
    response.raise_for_status()
    records = response.json()
    _stamp(records, country, topic, sentiment_type, index_type)
    return records


def fetch_historical_index(
    country: str,
    topic: str,
    sentiment_type: str,
    index_type: str,
    start_date: date,
    end_date: date | None = None,
) -> list[dict]:
    """
    Paginate through GET /v1/headlines/index/gmsi/historical/{country}.

    Uses keyset pagination: each response envelope has 'has_more' and 'next_token'.
    Loops until has_more is False. Supports up to 90 days of lookback.
    """
    url = f"{settings.base_url}/headlines/index/gmsi/historical/{country}"
    params: dict = {
        "topic": topic,
        "sentiment_type": sentiment_type,
        "index_type": index_type,
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
        _stamp(records, country, topic, sentiment_type, index_type)
        all_records.extend(records)
        logger.info(
            "  page %3d: %5d records  |  total so far: %6d",
            page,
            len(records),
            len(all_records),
        )
        if not body["has_more"]:
            break
        params["next_token"] = body["next_token"]
        page += 1

    return all_records
