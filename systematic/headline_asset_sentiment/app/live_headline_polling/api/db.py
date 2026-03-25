import sqlite3
from contextlib import contextmanager
from typing import Generator

from config import settings


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Read-only SQLite connection. The poller is the sole writer."""
    conn = sqlite3.connect(
        f"file:{settings.db_path}?mode=ro",
        uri=True,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
