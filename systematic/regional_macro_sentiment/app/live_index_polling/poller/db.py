import sqlite3
from contextlib import contextmanager
from datetime import date as _date
from typing import Generator

from config import settings


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
    """Create the macro_regional_sentiment table and index if they do not already exist."""
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS macro_regional_sentiment (
                publication_time  TEXT NOT NULL,
                topic_name        TEXT NOT NULL,
                country           TEXT NOT NULL,
                index_type        TEXT NOT NULL,
                headline_count    INTEGER,
                sentiment_avg     REAL,
                sentiment_sum     REAL,
                sentiment_std     REAL,
                fetched_at        TEXT,
                PRIMARY KEY (publication_time, topic_name, country, index_type)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mrs_country_time
            ON macro_regional_sentiment (country, publication_time)
        """)


def latest_publication_date(index_type: str) -> "_date | None":
    """
    Return the date of the most recent record for a given index_type, or None if empty.

    Used by the backfill logic to resume from where the DB left off rather than
    re-fetching the full BACKFILL_DAYS window on every container restart.
    """
    with connection() as conn:
        row = conn.execute(
            "SELECT MAX(publication_time) FROM macro_regional_sentiment WHERE index_type = ?",
            (index_type,),
        ).fetchone()

    raw = row[0] if row else None
    if not raw:
        return None
    try:
        return _date.fromisoformat(raw[:10])
    except ValueError:
        return None


def upsert_regional(records: list[dict]) -> int:
    """
    Upsert regional macro sentiment records into the local SQLite database.

    INSERT OR REPLACE ensures re-polling the same 2-hour live window does not
    create duplicate rows. Records are uniquely identified by the composite key
    (publication_time, topic_name, country, index_type).

    Returns the number of rows written.
    """
    if not records:
        return 0

    columns = [
        "publication_time", "topic_name", "country", "index_type",
        "headline_count", "sentiment_avg", "sentiment_sum", "sentiment_std", "fetched_at",
    ]
    placeholders = ", ".join(["?"] * len(columns))
    sql = (
        f"INSERT OR REPLACE INTO macro_regional_sentiment ({', '.join(columns)}) "
        f"VALUES ({placeholders})"
    )
    rows = [tuple(r.get(c) for c in columns) for r in records]

    with connection() as conn:
        conn.executemany(sql, rows)

    return len(rows)
