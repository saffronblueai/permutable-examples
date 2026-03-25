import sqlite3
from contextlib import contextmanager
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
    """Create the headline_index table and index if they do not already exist."""
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS headline_index (
                ticker            TEXT NOT NULL,
                publication_time  TEXT NOT NULL,
                topic_name        TEXT NOT NULL,
                index_type        TEXT NOT NULL,
                headline_count    INTEGER,
                sentiment_sum     REAL,
                sentiment_abs_sum REAL,
                sentiment_std     REAL,
                fetched_at        TEXT,
                PRIMARY KEY (ticker, publication_time, topic_name, index_type)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hi_ticker_time
            ON headline_index (ticker, publication_time)
        """)


def latest_publication_date(ticker: str) -> "date | None":
    """
    Return the date of the most recent index record for *ticker*, or None if
    the table is empty / the ticker has no rows yet.

    Used by the backfill logic to resume from where the DB left off rather
    than re-fetching the full BACKFILL_DAYS window on every container restart.
    """
    from datetime import date as _date

    with connection() as conn:
        row = conn.execute(
            "SELECT MAX(publication_time) FROM headline_index WHERE ticker = ?",
            (ticker,),
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
    Upsert headline index records into the local SQLite database.

    INSERT OR REPLACE ensures no duplicates when the 2-hour live window
    overlaps across consecutive polls. Records are uniquely identified by
    (ticker, publication_time, topic_name, index_type).

    Returns the number of rows written.
    """
    if not records:
        return 0

    columns = [
        "ticker", "publication_time", "topic_name", "index_type",
        "headline_count", "sentiment_sum", "sentiment_abs_sum",
        "sentiment_std", "fetched_at",
    ]
    placeholders = ", ".join(["?"] * len(columns))
    sql = (
        f"INSERT OR REPLACE INTO headline_index ({', '.join(columns)}) "
        f"VALUES ({placeholders})"
    )
    rows = [tuple(r.get(c) for c in columns) for r in records]

    with connection() as conn:
        conn.executemany(sql, rows)

    return len(rows)
