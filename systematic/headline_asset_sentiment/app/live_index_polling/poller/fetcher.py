import logging
from datetime import date, datetime, timezone

import requests

from config import settings

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {"x-api-key": settings.api_key}


def _stamp(records: list[dict]) -> None:
    """Add fetched_at timestamp to each record in-place."""
    ts = datetime.now(timezone.utc).isoformat()
    for r in records:
        r["fetched_at"] = ts


def _index_params(extra: dict | None = None) -> dict:
    """Base query parameters shared by both live and historical index endpoints."""
    params: dict = {
        "index_type": settings.index_type,
        "topic_preset": settings.topic_preset,
        "sparse": str(settings.sparse).lower(),
        "align_to_period_end": str(settings.align_to_period_end).lower(),
    }
    if extra:
        params.update(extra)
    return params


def fetch_live_index(ticker: str) -> list[dict]:
    """
    Fetch the live pre-aggregated headline sentiment index for a single ticker.

    Calls GET /v1/headlines/index/ticker/live/{ticker} and returns a flat list
    of record dicts matching the HeadlineIndex schema. The endpoint always
    returns the most recent 2-hour window of hourly buckets.
    """
    url = f"{settings.base_url}/headlines/index/ticker/live/{ticker}"
    response = requests.get(url, params=_index_params(), headers=_headers(), timeout=30)
    response.raise_for_status()
    records = response.json()
    _stamp(records)
    return records


def fetch_historical_index(
    ticker: str,
    start_date: date,
    end_date: date | None = None,
) -> list[dict]:
    """
    Paginate through GET /v1/headlines/index/ticker/historical/{ticker}.

    Uses keyset pagination: each response contains 'has_more' and 'next_token'.
    Loops until has_more is False, passing next_token into every subsequent request.
    Supports up to 90 days of lookback.
    """
    url = f"{settings.base_url}/headlines/index/ticker/historical/{ticker}"
    params = _index_params({"start_date": start_date.isoformat(), "limit": 1000})
    if end_date:
        params["end_date"] = end_date.isoformat()

    all_records: list[dict] = []
    page = 1

    while True:
        response = requests.get(url, params=params, headers=_headers(), timeout=30)
        response.raise_for_status()
        body = response.json()
        records = body["data"]
        _stamp(records)
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
