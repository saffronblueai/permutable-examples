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
    """Create the headline_sentiment table and index if they do not already exist."""
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS headline_sentiment (
                ticker               TEXT NOT NULL,
                publication_time     TEXT NOT NULL,
                topic_name           TEXT NOT NULL,
                ticker_name          TEXT,
                sentiment_score      REAL,
                bearish_probability  REAL,
                neutral_probability  REAL,
                bullish_probability  REAL,
                topic_probability    REAL,
                match_type           TEXT,
                language             TEXT,
                countries            TEXT,
                fetched_at           TEXT,
                PRIMARY KEY (ticker, publication_time, topic_name)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hs_ticker_time
            ON headline_sentiment (ticker, publication_time)
        """)


def latest_publication_date(ticker: str) -> "date | None":
    """
    Return the date of the most recent record for *ticker*, or None if the
    table is empty / the ticker has no rows yet.

    Used by the backfill logic to resume from where the DB left off rather
    than re-fetching the full BACKFILL_DAYS window on every container restart.
    """
    from datetime import date as _date  # local import avoids circular deps at module level

    with connection() as conn:
        row = conn.execute(
            "SELECT MAX(publication_time) FROM headline_sentiment WHERE ticker = ?",
            (ticker,),
        ).fetchone()

    raw = row[0] if row else None
    if not raw:
        return None

    # publication_time is stored as an ISO-8601 string; extract just the date part
    try:
        return _date.fromisoformat(raw[:10])
    except ValueError:
        return None


def upsert_headlines(records: list[dict]) -> int:
    """
    Upsert headline records into the local SQLite database.

    INSERT OR REPLACE ensures no duplicates when the 2-hour live window overlaps
    across consecutive polls. Records are uniquely identified by the composite key
    (ticker, publication_time, topic_name).

    Returns the number of rows written.
    """
    if not records:
        return 0

    columns = [
        "ticker", "publication_time", "topic_name", "ticker_name",
        "sentiment_score", "bearish_probability", "neutral_probability",
        "bullish_probability", "topic_probability", "match_type",
        "language", "countries", "fetched_at",
    ]
    placeholders = ", ".join(["?"] * len(columns))
    sql = (
        f"INSERT OR REPLACE INTO headline_sentiment ({', '.join(columns)}) "
        f"VALUES ({placeholders})"
    )
    rows = [tuple(r.get(c) for c in columns) for r in records]

    with connection() as conn:
        conn.executemany(sql, rows)

    return len(rows)
