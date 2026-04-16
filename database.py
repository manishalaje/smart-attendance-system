"""SQLite access layer for attendance, summaries, and fraud logs."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

DB_PATH = Path("attendance.db")


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with connection() as conn:
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
                subject TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                attendance_date TEXT NOT NULL,
                confidence REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_attendance
            ON attendance_logs(user_id, subject, attendance_date);

            CREATE TABLE IF NOT EXISTS fraud_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                name TEXT,
                alert_type TEXT NOT NULL,
                details TEXT,
                timestamp TEXT NOT NULL
            );
            """
        )


def upsert_user(user_id: str, name: str) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO users(user_id, name, created_at)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET name=excluded.name
            """,
            (user_id, name, utc_now_iso()),
        )


def delete_user(user_id: str) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM attendance_logs WHERE user_id = ?", (user_id,))


def log_fraud(alert_type: str, details: str, user_id: Optional[str] = None, name: Optional[str] = None) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO fraud_alerts(user_id, name, alert_type, details, timestamp)
            VALUES(?, ?, ?, ?, ?)
            """,
            (user_id, name, alert_type, details, utc_now_iso()),
        )


def mark_attendance(user_id: str, name: str, subject: str, confidence: float) -> Dict[str, Any]:
    today = datetime.now(timezone.utc).date().isoformat()
    now = utc_now_iso()

    with connection() as conn:
        duplicate = conn.execute(
            """
            SELECT id FROM attendance_logs
            WHERE user_id = ? AND subject = ? AND attendance_date = ?
            LIMIT 1
            """,
            (user_id, subject, today),
        ).fetchone()

        if duplicate:
            return {
                "created": False,
                "duplicate": True,
                "timestamp": now,
                "attendance_date": today,
            }

        conn.execute(
            """
            INSERT INTO attendance_logs(user_id, name, subject, timestamp, attendance_date, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, name, subject, now, today, confidence),
        )

    return {
        "created": True,
        "duplicate": False,
        "timestamp": now,
        "attendance_date": today,
    }


def attendance_summary() -> List[dict]:
    """Overall attendance per user as present/total + percentage.

    total classes = distinct attendance dates globally.
    present days = distinct dates user appeared in any subject.
    """
    with connection() as conn:
        rows = conn.execute(
            """
            WITH total_days AS (
                SELECT COUNT(DISTINCT attendance_date) AS total_classes FROM attendance_logs
            ),
            user_present AS (
                SELECT user_id, name, COUNT(DISTINCT attendance_date) AS present_days
                FROM attendance_logs
                GROUP BY user_id, name
            )
            SELECT
                up.user_id,
                up.name,
                up.present_days,
                td.total_classes,
                CASE
                    WHEN td.total_classes = 0 THEN 0
                    ELSE ROUND((up.present_days * 100.0) / td.total_classes, 2)
                END AS percentage
            FROM user_present up
            CROSS JOIN total_days td
            ORDER BY up.name ASC
            """
        ).fetchall()

    return [dict(r) for r in rows] if rows else []


def subject_wise_summary() -> List[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            WITH subject_totals AS (
                SELECT subject, COUNT(DISTINCT attendance_date) AS total_classes
                FROM attendance_logs
                GROUP BY subject
            ),
            per_user_subject AS (
                SELECT user_id, name, subject, COUNT(DISTINCT attendance_date) AS present_days
                FROM attendance_logs
                GROUP BY user_id, name, subject
            )
            SELECT
                pus.user_id,
                pus.name,
                pus.subject,
                pus.present_days,
                st.total_classes,
                CASE
                    WHEN st.total_classes = 0 THEN 0
                    ELSE ROUND((pus.present_days * 100.0) / st.total_classes, 2)
                END AS percentage
            FROM per_user_subject pus
            JOIN subject_totals st ON pus.subject = st.subject
            ORDER BY pus.subject ASC, pus.name ASC
            """
        ).fetchall()

    return [dict(r) for r in rows] if rows else []


def recent_logs(limit: int = 100) -> List[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT user_id, name, subject, timestamp, attendance_date, confidence
            FROM attendance_logs
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows] if rows else []


def fraud_logs(limit: int = 100) -> List[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT user_id, name, alert_type, details, timestamp
            FROM fraud_alerts
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows] if rows else []


def subject_options() -> List[str]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT subject
            FROM attendance_logs
            WHERE TRIM(subject) <> ''
            ORDER BY subject ASC
            """
        ).fetchall()
    return [r["subject"] for r in rows] if rows else []


def list_users() -> List[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT user_id, name, created_at
            FROM users
            ORDER BY name ASC
            """
        ).fetchall()
    return [dict(r) for r in rows] if rows else []
