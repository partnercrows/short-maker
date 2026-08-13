from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app.core.config import get_settings
from app.db.schema import SCHEMA_STATEMENTS


def init_db() -> None:
    with get_connection() as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        conn.commit()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()
