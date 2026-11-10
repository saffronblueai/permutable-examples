import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from config import settings

COLUMNS = [
    "row_key", "ticker", "match_type", "topic", "topic_probability",
    "short_term_sentiment_score", "medium_term_sentiment_score", "long_term_sentiment_score",
    "headline", "link", "source_name", "processed_at", "fetched_at",
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
    """Create the gcsi_headlines table and index if they do not already exist."""
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gcsi_headlines (
                row_key                     TEXT PRIMARY KEY,
                ticker                      TEXT NOT NULL,
                match_type                  TEXT,
                topic                       TEXT,
                topic_probability           REAL,
                short_term_sentiment_score  REAL,
                medium_term_sentiment_score REAL,
                long_term_sentiment_score   REAL,
                headline                    TEXT,
                link                        TEXT,
                source_name                 TEXT,
                processed_at             TEXT,
                fetched_at                  TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gcsi_headlines_ticker_time
            ON gcsi_headlines (ticker, processed_at)
        """)


def latest_processed_at(ticker: str) -> datetime | None:
    """Newest stored receipt time for *ticker*, used to resume the backfill after a restart."""
    with connection() as conn:
        row = conn.execute("SELECT MAX(processed_at) FROM gcsi_headlines WHERE ticker = ?", (ticker,)).fetchone()
    return datetime.fromisoformat(row[0]) if row and row[0] else None


def upsert_headlines(records: list[dict]) -> int:
    """
    Upsert GCSI headline records into the local SQLite database.

    Rows are keyed by row_key, so overlapping live windows and a re-run backfill
    never create duplicates. Returns the number of rows written.
    """
    if not records:
        return 0
    placeholders = ", ".join(["?"] * len(COLUMNS))
    sql = f"INSERT OR REPLACE INTO gcsi_headlines ({', '.join(COLUMNS)}) VALUES ({placeholders})"
    with connection() as conn:
        conn.executemany(sql, [tuple(r.get(c) for c in COLUMNS) for r in records])
    return len(records)
