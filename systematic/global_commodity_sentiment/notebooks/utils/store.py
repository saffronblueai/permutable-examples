"""SQLite storage for the GCSI notebooks. Every write is an upsert, so re-polling a window is harmless."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .api import HORIZONS, INDEX_VALUES, normalise_topic


def _utc_iso(value) -> str | None:
    if value is None:
        return None
    stamp = pd.Timestamp(value)
    return (stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")).isoformat()


class IndexStore:
    """Hourly index bars keyed on (ticker, topic, index type, horizon, hour)."""

    COLUMNS = ["ticker", "topic_name", "index_type", "sentiment_type", "processed_at", *INDEX_VALUES, "fetched_at"]

    def __init__(self, path: str | Path):
        self.path = Path(path)
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gcsi_index (
                    ticker          TEXT NOT NULL,
                    topic_name      TEXT NOT NULL,
                    index_type      TEXT NOT NULL,
                    sentiment_type  TEXT NOT NULL,
                    processed_at    TEXT NOT NULL,
                    headline_count  INTEGER,
                    sentiment_sum   REAL,
                    sentiment_std   REAL,
                    fetched_at      TEXT,
                    PRIMARY KEY (ticker, topic_name, index_type, sentiment_type, processed_at)
                )
            """)

    def upsert(self, records: list[dict]) -> int:
        """INSERT OR REPLACE, so a revised bar overwrites the earlier version of the same hour."""
        if not records:
            return 0
        fetched_at = datetime.now(timezone.utc).isoformat()
        rows = [
            tuple(_utc_iso(record["processed_at"]) if col == "processed_at"
                  else fetched_at if col == "fetched_at" else record.get(col) for col in self.COLUMNS)
            for record in records
        ]
        placeholders = ", ".join("?" * len(self.COLUMNS))
        with sqlite3.connect(self.path) as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO gcsi_index ({', '.join(self.COLUMNS)}) VALUES ({placeholders})", rows
            )
        return len(rows)

    def load(self, hours: int, index_type: str = "COMBINED") -> pd.DataFrame:
        """Bars for one index type from the last `hours` hours."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with sqlite3.connect(self.path) as conn:
            frame = pd.read_sql("SELECT * FROM gcsi_index WHERE processed_at >= ? AND index_type = ?",
                                conn, params=(since, index_type))
        frame["processed_at"] = pd.to_datetime(frame["processed_at"], utc=True, format="ISO8601")
        return frame


class FeedStore:
    """Headline feed rows. The feed has no row id, so each row is keyed on
    (ticker, topic, match type, processed time, link or headline)."""

    COLUMNS = ["row_key", "ticker", "match_type", "topic", "topic_probability", *HORIZONS,
               "matched_entity_types", "matched_entities", "country", "source_country", "language",
               "headline", "link", "source_name", "processed_at", "fetched_at"]
    REAL_COLUMNS = {"topic_probability", *HORIZONS}

    def __init__(self, path: str | Path):
        self.path = Path(path)
        columns = ", ".join(f"{c} {'REAL' if c in self.REAL_COLUMNS else 'TEXT'}" for c in self.COLUMNS)
        with sqlite3.connect(self.path) as conn:
            conn.execute(f"CREATE TABLE IF NOT EXISTS gcsi_headlines ({columns}, PRIMARY KEY (row_key))")

    @staticmethod
    def row_key(record: dict) -> str:
        parts = [record.get(k) or "" for k in ("ticker", "topic", "match_type", "processed_at")]
        parts.append(record.get("link") or record.get("headline") or "")
        return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()

    def upsert(self, records: list[dict]) -> int:
        if not records:
            return 0
        fetched_at = datetime.now(timezone.utc).isoformat()
        rows = [
            tuple(self.row_key(r) if c == "row_key" else fetched_at if c == "fetched_at" else r.get(c)
                  for c in self.COLUMNS)
            for r in records
        ]
        placeholders = ", ".join("?" * len(self.COLUMNS))
        with sqlite3.connect(self.path) as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO gcsi_headlines ({', '.join(self.COLUMNS)}) VALUES ({placeholders})", rows
            )
        return len(rows)

    def load(self, hours: int) -> pd.DataFrame:
        """Headlines processed in the last `hours` hours."""
        with sqlite3.connect(self.path) as conn:
            frame = pd.read_sql("SELECT * FROM gcsi_headlines", conn)
        frame["processed_at"] = pd.to_datetime(frame["processed_at"], utc=True, format="ISO8601")
        frame["topic"] = normalise_topic(frame["topic"])
        since = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=hours)
        return frame[frame["processed_at"] >= since].reset_index(drop=True)
