"""Database helpers for attendance, events, and dashboard metrics."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

DB_PATH = Path("attendance.db")


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attendance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                confidence REAL NOT NULL,
                session_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS fraud_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                name TEXT,
                alert_type TEXT NOT NULL,
                details TEXT,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS unknown_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                confidence REAL,
                timestamp TEXT NOT NULL
            );
            """
        )


def upsert_user(user_id: str, name: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, name, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET name=excluded.name
            """,
            (user_id, name, now),
        )


def last_attendance(user_id: str) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM attendance_logs
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    return row


def has_attendance_in_session(user_id: str, session_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM attendance_logs
            WHERE user_id = ? AND session_id = ?
            LIMIT 1
            """,
            (user_id, session_id),
        ).fetchone()
    return row is not None


def log_attendance(user_id: str, name: str, confidence: float, session_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO attendance_logs (user_id, name, timestamp, confidence, session_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, name, now, confidence, session_id),
        )


def log_fraud(alert_type: str, details: str, user_id: Optional[str] = None, name: Optional[str] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO fraud_alerts (user_id, name, alert_type, details, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, name, alert_type, details, now),
        )


def log_unknown_attempt(confidence: float) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO unknown_attempts (confidence, timestamp)
            VALUES (?, ?)
            """,
            (confidence, now),
        )


def recent_duplicate(user_id: str, minutes: int = 5) -> bool:
    row = last_attendance(user_id)
    if row is None:
        return False

    last_ts = datetime.fromisoformat(row["timestamp"])
    now = datetime.now(timezone.utc)
    return (now - last_ts) < timedelta(minutes=minutes)


def dashboard_stats() -> Dict[str, List[dict]]:
    with get_connection() as conn:
        totals = conn.execute(
            """
            SELECT user_id, name, COUNT(*) as total_attendance
            FROM attendance_logs
            GROUP BY user_id, name
            ORDER BY total_attendance DESC
            """
        ).fetchall()

        daily = conn.execute(
            """
            SELECT user_id, name, timestamp, confidence
            FROM attendance_logs
            ORDER BY timestamp DESC
            LIMIT 100
            """
        ).fetchall()

        alerts = conn.execute(
            """
            SELECT user_id, name, alert_type, details, timestamp
            FROM fraud_alerts
            ORDER BY timestamp DESC
            LIMIT 100
            """
        ).fetchall()

    return {
        "totals": [dict(r) for r in totals],
        "daily_logs": [dict(r) for r in daily],
        "fraud_alerts": [dict(r) for r in alerts],
    }
