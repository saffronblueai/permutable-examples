import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from config import settings

COLUMNS = [
    "ticker", "topic_name", "topic_id", "index_type", "sentiment_type", "extraction_time",
    "headline_count", "sentiment_sum", "sentiment_abs_sum", "sentiment_std", "fetched_at",
]


@contextmanager
def connection() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def setup_database() -> None:
    """Create the gcsi_index table and index if they do not already exist."""
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gcsi_index (
                ticker            TEXT NOT NULL,
                topic_name        TEXT NOT NULL,
                topic_id          TEXT,
                index_type        TEXT NOT NULL,
                sentiment_type    TEXT NOT NULL,
                extraction_time   TEXT NOT NULL,
                headline_count    INTEGER,
                sentiment_sum     REAL,
                sentiment_abs_sum REAL,
                sentiment_std     REAL,
                fetched_at        TEXT,
                PRIMARY KEY (ticker, topic_name, index_type, sentiment_type, extraction_time)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gcsi_ticker_time
            ON gcsi_index (ticker, sentiment_type, index_type, extraction_time)
        """)


def latest_extraction_time(ticker: str, index_type: str, sentiment_type: str) -> datetime | None:
    """
    Return the newest stored bar for one series, or None if it has no rows yet.

    Used by the backfill logic to resume from where the DB left off rather than
    re-fetching the full BACKFILL_DAYS window on every container restart.
    """
    with connection() as conn:
        row = conn.execute(
            "SELECT MAX(extraction_time) FROM gcsi_index WHERE ticker = ? AND index_type = ? AND sentiment_type = ?",
            (ticker, index_type, sentiment_type),
        ).fetchone()
    return datetime.fromisoformat(row[0]) if row and row[0] else None


def upsert_index(records: list[dict]) -> int:
    """
    Upsert GCSI index records into the local SQLite database.

    INSERT OR REPLACE means a revised hourly bar overwrites the earlier version
    of the same hour, and overlapping live windows never create duplicates.
    Returns the number of rows written.
    """
    if not records:
        return 0
    placeholders = ", ".join(["?"] * len(COLUMNS))
    sql = f"INSERT OR REPLACE INTO gcsi_index ({', '.join(COLUMNS)}) VALUES ({placeholders})"
    with connection() as conn:
        conn.executemany(sql, [tuple(r.get(c) for c in COLUMNS) for r in records])
    return len(records)
