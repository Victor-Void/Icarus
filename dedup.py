"""SQLite-backed dedup store so entries are only posted once."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone

DB_PATH = "state.db"

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS posted (
    guid      TEXT NOT NULL,
    feed_url  TEXT NOT NULL,
    posted_at TEXT NOT NULL,
    PRIMARY KEY (guid, feed_url)
);
CREATE INDEX IF NOT EXISTS idx_posted_feed ON posted (feed_url);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def is_posted(guid: str, feed_url: str, db_path: str | None = None) -> bool:
    if db_path is None:
        db_path = DB_PATH
    with _lock, _connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM posted WHERE guid = ? AND feed_url = ?", (guid, feed_url)
        ).fetchone()
        return row is not None


def mark_posted(guid: str, feed_url: str, db_path: str | None = None) -> None:
    if db_path is None:
        db_path = DB_PATH
    with _lock, _connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO posted (guid, feed_url, posted_at) VALUES (?, ?, ?)",
            (guid, feed_url, _now()),
        )


def mark_posted_many(items: list[tuple[str, str]], db_path: str | None = None) -> None:
    if db_path is None:
        db_path = DB_PATH
    with _lock, _connect(db_path) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO posted (guid, feed_url, posted_at) VALUES (?, ?, ?)",
            [(guid, feed_url, _now()) for guid, feed_url in items],
        )


def count(db_path: str | None = None) -> int:
    if db_path is None:
        db_path = DB_PATH
    with _lock, _connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM posted").fetchone()[0]


def prune(db_path: str | None = None, keep_days: int = 90) -> int:
    if db_path is None:
        db_path = DB_PATH
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
    with _lock, _connect(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM posted WHERE posted_at < ?", (cutoff,)
        )
        return cur.rowcount


def count_for_feed(feed_url: str, db_path: str | None = None) -> int:
    if db_path is None:
        db_path = DB_PATH
    with _lock, _connect(db_path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM posted WHERE feed_url = ?", (feed_url,)
        ).fetchone()[0]


def oldest_date(db_path: str | None = None) -> str | None:
    if db_path is None:
        db_path = DB_PATH
    with _lock, _connect(db_path) as conn:
        return conn.execute("SELECT MIN(posted_at) FROM posted").fetchone()[0]
