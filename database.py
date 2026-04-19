import sqlite3

DB_PATH = "attendance.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        subject TEXT,
        date TEXT
    )
    """)

    conn.commit()
    conn.close()


def dashboard_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT name, subject, date FROM attendance ORDER BY id DESC
    """)

    data = cursor.fetchall()
    conn.close()
    return data


def attendance_summary():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # total classes per subject
    cursor.execute("""
    SELECT subject, COUNT(DISTINCT date) FROM attendance GROUP BY subject
    """)
    subject_totals = dict(cursor.fetchall())

    # student attendance
    cursor.execute("""
    SELECT name, subject, COUNT(*) FROM attendance GROUP BY name, subject
    """)
    rows = cursor.fetchall()

    summary = []

    for name, subject, present in rows:
        total = subject_totals.get(subject, 1)

        summary.append({
            "name": name,
            "subject": subject,
            "present": present,
            "total": total,
            "percentage": round((present / total) * 100, 2)
        })

    conn.close()
    return summary