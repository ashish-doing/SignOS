"""
memory_store.py — local-only event/routine memory (blueprint section 8).
SQLite at state/signos_memory.db. Stores one row per action that actually
executed: when, resolved mode, foreground app, source intent, action run.
No raw video, no frames, no camera data — ever. This is the data
routine_engine.py reads to build the day/time pattern model.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "state" / "signos_memory.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    ts REAL NOT NULL,
    day_of_week INTEGER NOT NULL,   -- 0=Monday .. 6=Sunday
    bucket INTEGER NOT NULL,        -- 0..95, 15-minute buckets
    mode TEXT NOT NULL,
    app TEXT NOT NULL,
    intent TEXT NOT NULL,
    action TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_bucket ON events(day_of_week, bucket);
"""

_lock = threading.Lock()


def bucket_index(dt: datetime) -> int:
    return (dt.hour * 60 + dt.minute) // 15


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.executescript(_SCHEMA)
    return conn


class MemoryStore:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self._conn = _connect()

    def log_event(self, mode: str, app: str, intent: str, action: str, when: datetime | None = None) -> None:
        when = when or datetime.now()
        with _lock:
            self._conn.execute(
                "INSERT INTO events (ts, day_of_week, bucket, mode, app, intent, action) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (when.timestamp(), when.weekday(), bucket_index(when), mode, app, intent, action),
            )
            self._conn.commit()

    def mode_counts_for_bucket(self, day_of_week: int, bucket: int) -> dict:
        with _lock:
            rows = self._conn.execute(
                "SELECT mode, COUNT(*) FROM events WHERE day_of_week=? AND bucket=? GROUP BY mode",
                (day_of_week, bucket),
            ).fetchall()
        return {mode: n for mode, n in rows}

    def total_events(self) -> int:
        with _lock:
            return self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def recent_daily_summary(self, limit_days: int = 7) -> list:
        with _lock:
            rows = self._conn.execute(
                "SELECT date(ts, 'unixepoch', 'localtime') AS d, COUNT(*) FROM events "
                "GROUP BY d ORDER BY d DESC LIMIT ?",
                (limit_days,),
            ).fetchall()
        return [{"date": d, "count": n} for d, n in rows]