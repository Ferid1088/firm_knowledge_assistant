"""SQLite connection + schema initialization for multi-user persistence.

Local substitute for the spec's Postgres store: same relational shape, no
external service, fits the air-gapped pilot. One connection per call (SQLite
handles concurrent readers fine at pilot scale; writers serialize via SQLite's
own locking).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.config import DATABASE_PATH

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    schema = _SCHEMA_PATH.read_text()
    conn = get_connection()
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()
