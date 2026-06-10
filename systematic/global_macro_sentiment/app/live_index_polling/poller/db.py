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
    """Create the gmsi_index table and index if they do not already exist."""
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gmsi_index (
                country           TEXT NOT NULL,
                topic             TEXT NOT NULL,
                sentiment_type    TEXT NOT NULL,
                index_type        TEXT NOT NULL,
                publication_time  TEXT NOT NULL,
                headline_count    INTEGER,
                sentiment_sum     REAL,
                sentiment_abs_sum REAL,
                sentiment_std     REAL,
                fetched_at        TEXT,
                PRIMARY KEY (country, topic, sentiment_type, index_type, publication_time)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gmsi_idx_country_time
            ON gmsi_index (country, publication_time)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gmsi_idx_sentiment_type
            ON gmsi_index (sentiment_type, index_type)
        """)


def latest_publication_date(
    country: str, topic: str, sentiment_type: str, index_type: str,
) -> "_date | None":
    """
    Return the date of the most recent record for a given combination, or None.

    Used by backfill to resume from where the DB left off rather than
    re-fetching the full BACKFILL_DAYS window on every container restart.
    """
    with connection() as conn:
        row = conn.execute(
            """SELECT MAX(publication_time) FROM gmsi_index
               WHERE country = ? AND topic = ? AND sentiment_type = ? AND index_type = ?""",
            (country, topic, sentiment_type, index_type),
        ).fetchone()

    raw = row[0] if row else None
    if not raw:
        return None
    try:
        return _date.fromisoformat(raw[:10])
    except ValueError:
        return None


def upsert_index(records: list[dict]) -> int:
    """
    Upsert GMSI hourly index records into the local SQLite database.

    INSERT OR REPLACE ensures re-polling the same live window does not create
    duplicate rows. Records are uniquely identified by the composite key
    (country, topic, sentiment_type, index_type, publication_time).

    Returns the number of rows written.
    """
    if not records:
        return 0

    columns = [
        "country", "topic", "sentiment_type", "index_type", "publication_time",
        "headline_count", "sentiment_sum", "sentiment_abs_sum", "sentiment_std",
        "fetched_at",
    ]
    placeholders = ", ".join(["?"] * len(columns))
    sql = (
        f"INSERT OR REPLACE INTO gmsi_index ({', '.join(columns)}) "
        f"VALUES ({placeholders})"
    )
    rows = [tuple(r.get(c) for c in columns) for r in records]

    with connection() as conn:
        conn.executemany(sql, rows)

    return len(rows)
