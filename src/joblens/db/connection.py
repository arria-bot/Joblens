"""SQLite connection factory.

Every connection gets the pragmas the project relies on: foreign keys (off by
default in SQLite!), WAL for concurrency, a busy timeout so a second process
waits instead of failing, and ``Row`` so callers can use column names.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from joblens.config import get_db_path


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    if db_path is None:
        return Path(get_db_path())
    return Path(db_path)


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def get_conn(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Connection scope: commit on success, roll back on error, always close."""
    conn = connect(db_path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()
