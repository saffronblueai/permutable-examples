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
    """Create the gmsi_headlines table and index if they do not already exist."""
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gmsi_headlines (
                country                      TEXT NOT NULL,
                topic                        TEXT NOT NULL,
                match_type                   TEXT NOT NULL,
                publication_time             TEXT NOT NULL,
                topic_probability            REAL,
                directional_positive         REAL,
                directional_neutral          REAL,
                directional_negative         REAL,
                directional_score            REAL,
                semantic_sentiment_positive  REAL,
                semantic_sentiment_neutral   REAL,
                semantic_sentiment_negative  REAL,
                semantic_sentiment_score     REAL,
                fetched_at                   TEXT,
                PRIMARY KEY (country, topic, match_type, publication_time)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gmsi_hl_country_time
            ON gmsi_headlines (country, publication_time)
        """)


def latest_publication_date(country: str, topic: str, match_type: str) -> "_date | None":
    """
    Return the date of the most recent record for a given combination, or None.

    Used by backfill to resume from where the DB left off rather than
    re-fetching the full BACKFILL_DAYS window on every container restart.
    """
    with connection() as conn:
        row = conn.execute(
            """SELECT MAX(publication_time) FROM gmsi_headlines
               WHERE country = ? AND topic = ? AND match_type = ?""",
            (country, topic, match_type),
        ).fetchone()

    raw = row[0] if row else None
    if not raw:
        return None
    try:
        return _date.fromisoformat(raw[:10])
    except ValueError:
        return None


def upsert_headlines(records: list[dict]) -> int:
    """
    Upsert GMSI headline records into the local SQLite database.

    INSERT OR REPLACE ensures re-polling the same live window does not create
    duplicate rows. Records are uniquely identified by the composite key
    (country, topic, match_type, publication_time).

    Returns the number of rows written.
    """
    if not records:
        return 0

    columns = [
        "country", "topic", "match_type", "publication_time",
        "topic_probability",
        "directional_positive", "directional_neutral", "directional_negative",
        "directional_score",
        "semantic_sentiment_positive", "semantic_sentiment_neutral",
        "semantic_sentiment_negative", "semantic_sentiment_score",
        "fetched_at",
    ]
    placeholders = ", ".join(["?"] * len(columns))
    sql = (
        f"INSERT OR REPLACE INTO gmsi_headlines ({', '.join(columns)}) "
        f"VALUES ({placeholders})"
    )
    rows = [tuple(r.get(c) for c in columns) for r in records]

    with connection() as conn:
        conn.executemany(sql, rows)

    return len(rows)
