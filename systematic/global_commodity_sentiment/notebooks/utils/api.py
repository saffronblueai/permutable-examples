"""Permutable API access for the GCSI notebooks: API key, retries, pagination and the GCSI routes."""

from __future__ import annotations

import getpass
import os
import random
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

DEFAULT_BASE_URL = "https://copilot-api.permutable.ai/v1"

# GCSI routes. The ticker and topic are query presets, not part of the path.
INDEX_LIVE_PATH = "/headlines/index/gcsi/live"
INDEX_HISTORICAL_PATH = "/headlines/index/gcsi/historical"
FEED_LIVE_PATH = "/headlines/feed/live/gcsi"
FEED_HISTORICAL_PATH = "/headlines/feed/historical/gcsi"
PAGE_LIMIT = 1000
MAX_LOOKBACK_DAYS = 90

SENTIMENT_TYPES = ["short_term", "medium_term", "long_term"]
HORIZONS = ["short_term_sentiment_score", "medium_term_sentiment_score", "long_term_sentiment_score"]
INDEX_VALUES = ["headline_count", "sentiment_sum", "sentiment_std"]
TOPIC_SEPARATOR = "::"  # Sector::L1::L2, the form the API returns
LIST_SEPARATOR = "|"  # matched_entity_types, matched_entities and country hold |-separated lists


def load_env_file() -> None:
    """Read KEY=VALUE pairs from the nearest .env file without overriding variables already set."""
    for base in [Path.cwd(), *Path.cwd().parents]:
        env_path = base / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"'))
            return


def get_api_key() -> str:
    """API_KEY or PERMUTABLE_API_KEY from the environment or a .env file, otherwise a prompt."""
    load_env_file()
    key = os.environ.get("API_KEY") or os.environ.get("PERMUTABLE_API_KEY")
    if not key:
        key = getpass.getpass("Enter your Permutable AI API key: ")
    return key


def _date(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return (value.date() if isinstance(value, datetime) else value).isoformat()


def _records(body) -> list[dict]:
    """Live endpoints return a list; historical endpoints return {data, has_more, next_token}."""
    return body["data"] if isinstance(body, dict) else body


def _stamp(records: list[dict], **dims) -> list[dict]:
    """Responses can omit the dimensions you asked for, so write them back onto each record."""
    for record in records:
        for key, value in dims.items():
            if value is not None:
                record.setdefault(key, value)
    return records


class GcsiClient:
    """The GCSI index and headline routes, with exponential backoff on 429 and 5xx responses."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, max_retries: int = 5):
        self.base_url = base_url or os.environ.get("BASE_URL", DEFAULT_BASE_URL)
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"x-api-key": api_key or get_api_key(), "accept": "application/json"})

    def get(self, path: str, params: dict | None = None):
        """GET a Permutable API path, backing off exponentially (with jitter) on 429 and 5xx responses."""
        params = {k: v for k, v in (params or {}).items() if v is not None}
        delay = 1.0
        for attempt in range(self.max_retries + 1):
            response = self.session.get(self.base_url + path, params=params, timeout=60)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self.max_retries:
                    response.raise_for_status()
                time.sleep(delay + random.uniform(0, delay / 2))
                delay *= 2
                continue
            if response.status_code in (401, 403):
                raise PermissionError(
                    f"{response.status_code} on {path}: check the API key, and that your licence includes GCSI."
                )
            response.raise_for_status()
            return response.json()

    def paginate(self, path: str, params: dict) -> list[dict]:
        """Follow next_token until has_more is false."""
        params = {**params, "limit": PAGE_LIMIT}
        rows: list[dict] = []
        while True:
            body = self.get(path, params)
            rows.extend(_records(body))
            if not (isinstance(body, dict) and body.get("has_more")):
                return rows
            params["next_token"] = body["next_token"]

    # ── Hourly index ────────────────────────────────────────────────────────

    @staticmethod
    def _index_params(ticker: str, index_type: str, sentiment_type: str) -> dict:
        # One ticker per call with every topic. A sector preset or ticker_preset=ALL can exceed the 1000-row live cap.
        return {"ticker_preset": ticker, "topic_preset": "ALL", "index_type": index_type,
                "sentiment_type": sentiment_type}

    def index_live(self, ticker: str, index_type: str = "COMBINED", sentiment_type: str = "short_term") -> list[dict]:
        """Last 24 hours of hourly bars. The newest bars can still be revised."""
        body = self.get(INDEX_LIVE_PATH, self._index_params(ticker, index_type, sentiment_type))
        return _stamp(_records(body), ticker=ticker, index_type=index_type, sentiment_type=sentiment_type)

    def index_history(self, ticker: str, start: date | datetime, end: date | datetime | None = None,
                      index_type: str = "COMBINED", sentiment_type: str = "short_term") -> list[dict]:
        """Hourly bars between start and end (inclusive dates), at most 90 days."""
        params = {**self._index_params(ticker, index_type, sentiment_type),
                  "start_date": _date(start), "end_date": _date(end)}
        rows = self.paginate(INDEX_HISTORICAL_PATH, params)
        return _stamp(rows, ticker=ticker, index_type=index_type, sentiment_type=sentiment_type)

    # ── Headline feed ───────────────────────────────────────────────────────

    def feed_live(self, ticker: str, match_type: str | None = None,
                  entity_type_preset: str | None = None) -> list[dict]:
        """Last 24 hours of headlines, one row per headline × commodity × topic."""
        params = {"ticker_preset": ticker, "match_type": match_type,
                  "matched_entity_type_preset": entity_type_preset, "limit": PAGE_LIMIT}
        return _stamp(_records(self.get(FEED_LIVE_PATH, params)), ticker=ticker)

    def feed_history(self, ticker: str, start: date | datetime, end: date | datetime | None = None,
                     match_type: str | None = None, entity_type_preset: str | None = None) -> list[dict]:
        """Headlines between start and end (inclusive dates), at most 90 days."""
        params = {"ticker_preset": ticker, "match_type": match_type, "matched_entity_type_preset": entity_type_preset,
                  "start_date": _date(start), "end_date": _date(end)}
        return _stamp(self.paginate(FEED_HISTORICAL_PATH, params), ticker=ticker)


def normalise_topic(labels: pd.Series) -> pd.Series:
    """Write each label as sector, driver and topic joined by TOPIC_SEPARATOR, whatever separator the source used."""
    return labels.astype("string").str.replace(r"\s*(?:::|-)\s*", TOPIC_SEPARATOR, regex=True)


def to_index_frame(records: list[dict]) -> pd.DataFrame:
    """Index records → DataFrame with a UTC processed_at and every value column present."""
    frame = pd.DataFrame(records)
    for column in ["ticker", "topic_name", "index_type", "sentiment_type", "processed_at", *INDEX_VALUES]:
        if column not in frame:
            frame[column] = np.nan
    frame["processed_at"] = pd.to_datetime(frame["processed_at"], utc=True, format="ISO8601")
    frame["topic_name"] = normalise_topic(frame["topic_name"])
    return frame


def to_feed_frame(records: list[dict]) -> pd.DataFrame:
    """Feed records → DataFrame with a UTC processed_at and normalised topic labels."""
    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    frame["processed_at"] = pd.to_datetime(frame["processed_at"], utc=True, format="ISO8601")
    frame["topic"] = normalise_topic(frame["topic"])
    return frame
