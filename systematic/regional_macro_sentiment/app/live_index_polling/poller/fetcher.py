import logging
from datetime import date, datetime, timezone

import requests
from config import settings

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {"x-api-key": settings.api_key}


def _stamp(records: list[dict], index_type: str) -> None:
    """Add fetched_at timestamp and explicit index_type to each record in-place."""
    ts = datetime.now(timezone.utc).isoformat()
    for r in records:
        r["fetched_at"] = ts
        r["index_type"] = index_type


def fetch_live_regional(index_type: str) -> list[dict]:
    """
    Fetch the live regional macro sentiment index for one index_type.

    Calls GET /v1/headlines/index/macro/live/regional/{model_id} and returns a
    flat list of record dicts. A single call covers all countries in the
    configured country_preset — no per-country loop needed.
    """
    url = f"{settings.base_url}/headlines/index/macro/live/regional/{settings.model_id}"
    response = requests.get(
        url, params={**settings.base_params, "index_type": index_type},
        headers=_headers(), timeout=30,
    )
    response.raise_for_status()
    records = response.json()
    _stamp(records, index_type)
    return records


def fetch_historical_regional(
    start_date: date,
    index_type: str,
    end_date: date | None = None,
) -> list[dict]:
    """
    Paginate through GET /v1/headlines/index/macro/historical/regional/{model_id}.

    Uses keyset pagination: each response contains 'has_more' and 'next_token'.
    Loops until has_more is False. Supports up to 90 days of lookback.
    """
    url = f"{settings.base_url}/headlines/index/macro/historical/regional/{settings.model_id}"
    params = {
        **settings.base_params,
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
        _stamp(records, index_type)
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
