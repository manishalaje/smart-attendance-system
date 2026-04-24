from flask import Flask, render_template, request, jsonify, redirect, session
import os
import base64
import numpy as np
import io
import sqlite3
from datetime import datetime
from PIL import Image

# ===============================
# OPTIONAL POSTGRES
# ===============================
USE_POSTGRES = False
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    try:
        import psycopg2
        from psycopg2 import Binary
        USE_POSTGRES = True
    except:
        USE_POSTGRES = False

# ===============================
# APP CONFIG
# ===============================
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", "secret123")

# ===============================
# AI MODE
# ===============================
USE_AI = os.getenv("USE_AI", "True").lower() == "true"

FACE_AVAILABLE = False
try:
    if USE_AI:
        import face_recognition
        FACE_AVAILABLE = True
except:
    print("face_recognition not available")

# ===============================
# DATABASE
# ===============================
def get_conn():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    else:
        return sqlite3.connect("attendance.db")


def qmark():
    return "%s" if USE_POSTGRES else "?"


def blob_data(data):
    if USE_POSTGRES:
        return Binary(data)
    return data


# ===============================
# INIT DB
# ===============================
def init_db():
    conn = get_conn()
    c = conn.cursor()

    auto = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    blob = "BYTEA" if USE_POSTGRES else "BLOB"

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS users(
        id {auto},
        name TEXT UNIQUE,
        encoding {blob}
    )
    """)

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS attendance(
        id {auto},
        name TEXT,
        subject TEXT,
        date TEXT
    )
    """)

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS accounts(
        id {auto},
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    )
    """)

    conn.commit()
    conn.close()


def create_admin():
    conn = get_conn()
    c = conn.cursor()

    p = qmark()

    c.execute(f"SELECT * FROM accounts WHERE username={p}", ("admin",))
    row = c.fetchone()

    if not row:
        c.execute(
            f"INSERT INTO accounts(username,password,role) VALUES({p},{p},{p})",
            ("admin", "admin123", "admin")
        )

    conn.commit()
    conn.close()


init_db()
create_admin()

# ===============================
# IMAGE HELPERS
# ===============================
def decode_image(data):
    data = data.split(",")[1]
    img_bytes = base64.b64decode(data)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    return np.array(img)


def get_encoding(img):
    if not USE_AI or not FACE_AVAILABLE:
        return None

    img = np.ascontiguousarray(img, dtype=np.uint8)
    loc = face_recognition.face_locations(img)

    if not loc:
        return None

    enc = face_recognition.face_encodings(img, loc)
    return enc[0], loc[0]


# ===============================
# AUTH
# ===============================
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = get_conn()
        c = conn.cursor()
        qm = qmark()

        c.execute(f"SELECT * FROM accounts WHERE username={qm}", (u,))
        if c.fetchone():
            conn.close()
            return "User already exists"

        c.execute(
            f"INSERT INTO accounts(username,password,role) VALUES({qm},{qm},{qm})",
            (u, p, "student")
        )

        conn.commit()
        conn.close()
        return redirect("/login")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = get_conn()
        c = conn.cursor()
        qm = qmark()

        c.execute(
            f"SELECT * FROM accounts WHERE username={qm} AND password={qm}",
            (u, p)
        )

        user = c.fetchone()
        conn.close()

        if user:
            session["user"] = u
            session["role"] = user[3]

            if user[3] == "admin":
                return redirect("/")
            return redirect("/student")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ===============================
# HOME DASHBOARD
# ===============================
@app.route("/")
def home():
    if "user" not in session or session.get("role") != "admin":
        return redirect("/login")

    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT name,subject,date FROM attendance ORDER BY id DESC")
    logs = c.fetchall()

    c.execute("SELECT COUNT(*) FROM users")
    total_students = c.fetchone()[0]

    today = str(datetime.now().date())

    qm = qmark()

    c.execute(f"SELECT COUNT(DISTINCT name) FROM attendance WHERE date={qm}", (today,))
    present_total = c.fetchone()[0]

    subjects = ["AI", "Math", "DBMS"]
    summary = []
    subject_counts = []

    for sub in subjects:
        c.execute(
            f"SELECT COUNT(DISTINCT name) FROM attendance WHERE subject={qm} AND date={qm}",
            (sub, today)
        )

        present = c.fetchone()[0]
        pct = int((present / total_students) * 100) if total_students else 0
        pct = min(pct, 100)

        summary.append({
            "subject": sub,
            "present": present,
            "percentage": pct
        })

        subject_counts.append(present)

    # TOP STUDENTS
    c.execute("SELECT COUNT(DISTINCT date) FROM attendance")
    total_days = c.fetchone()[0]
    total_possible = max(total_days * len(subjects), 1)

    c.execute("""
        SELECT name, COUNT(*) total
        FROM attendance
        GROUP BY name
        ORDER BY total DESC
        LIMIT 3
    """)

    rows = c.fetchall()
    top_students = []

    for row in rows:
        pct = int((row[1] / total_possible) * 100)
        pct = min(pct, 100)

        top_students.append({
            "name": row[0],
            "percentage": pct
        })

    conn.close()

    return render_template(
        "dashboard.html",
        logs=logs,
        total_students=total_students,
        present_total=present_total,
        absent=max(total_students - present_total, 0),
        summary=summary,
        subject_counts=subject_counts,
        top_students=top_students
    )


# ===============================
# STUDENT PAGE
# ===============================
@app.route("/student")
def student():
    if "user" not in session:
        return redirect("/login")
    return render_template("student.html")


@app.route("/student_dashboard")
def student_dashboard():
    if "user" not in session:
        return jsonify({"error": "login required"})

    name = session["user"]

    conn = get_conn()
    c = conn.cursor()
    qm = qmark()

    c.execute(
        f"SELECT subject,date FROM attendance WHERE name={qm}",
        (name,)
    )

    logs = c.fetchall()
    total = len(logs)

    days = len(set([str(x[1]) for x in logs]))
    possible = max(days * 3, 1)

    pct = int((total / possible) * 100) if total else 0
    pct = min(pct, 100)

    subs = ["AI", "Math", "DBMS"]
    subject_data = []

    for s in subs:
        count = len([x for x in logs if x[0] == s])
        sp = int((count / total) * 100) if total else 0

        subject_data.append({
            "subject": s,
            "percentage": sp
        })

    conn.close()

    return jsonify({
        "percentage": pct,
        "subjects": subject_data,
        "logs": [{"subject": x[0], "date": str(x[1])} for x in logs]
    })


# ===============================
# LIVE DATA
# ===============================
@app.route("/live_data")
def live_data():
    conn = get_conn()
    c = conn.cursor()

    subjects = ["AI", "Math", "DBMS"]
    counts = []

    qm = qmark()

    for s in subjects:
        c.execute(
            f"SELECT COUNT(DISTINCT name) FROM attendance WHERE subject={qm}",
            (s,)
        )
        counts.append(c.fetchone()[0])

    conn.close()

    return jsonify({
        "subjects": subjects,
        "counts": counts
    })


# ===============================
# REGISTER FACE
# ===============================
@app.route("/register_image", methods=["POST"])
def register_image():
    data = request.json
    name = data.get("name", "").strip()

    if not name:
        return jsonify({"message": "Name required"})

    if not USE_AI:
        return jsonify({"message": "Registered (Demo Mode)"})

    img = decode_image(data["image"])
    res = get_encoding(img)

    if not res:
        return jsonify({"message": "No face detected"})

    enc, _ = res

    conn = get_conn()
    c = conn.cursor()
    qm = qmark()

    c.execute(f"DELETE FROM users WHERE name={qm}", (name,))
    c.execute(
        f"INSERT INTO users(name,encoding) VALUES({qm},{qm})",
        (name, blob_data(enc.tobytes()))
    )

    conn.commit()
    conn.close()

    return jsonify({"message": "Registered successfully"})


# ===============================
# MARK ATTENDANCE
# ===============================
@app.route("/recognize_image", methods=["POST"])
def recognize_image():
    subject = request.json.get("subject")
    today = str(datetime.now().date())
    qm = qmark()

    if not USE_AI:
        name = "Demo User"

        conn = get_conn()
        c = conn.cursor()

        c.execute(
            f"SELECT * FROM attendance WHERE name={qm} AND subject={qm} AND date={qm}",
            (name, subject, today)
        )

        if not c.fetchone():
            c.execute(
                f"INSERT INTO attendance(name,subject,date) VALUES({qm},{qm},{qm})",
                (name, subject, today)
            )
            conn.commit()

        conn.close()

        return jsonify({
            "success": True,
            "name": name,
            "message": "Marked (Demo Mode)",
            "box": None
        })

    img = decode_image(request.json["image"])
    res = get_encoding(img)

    if not res:
        return jsonify({"success": False, "message": "No face", "box": None})

    enc, (top, right, bottom, left) = res

    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT name,encoding FROM users")
    users = c.fetchall()

    best_name = None
    best = 999

    for row in users:
        db = np.frombuffer(row[1], dtype=np.float64)
        dist = np.linalg.norm(enc - db)

        if dist < best:
            best = dist
            best_name = row[0]

    if best > 0.5:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Unknown",
            "box": [top, right, bottom, left]
        })

    c.execute(
        f"SELECT * FROM attendance WHERE name={qm} AND subject={qm} AND date={qm}",
        (best_name, subject, today)
    )

    if c.fetchone():
        conn.close()
        return jsonify({
            "success": True,
            "name": best_name,
            "message": "Already marked",
            "box": [top, right, bottom, left]
        })

    c.execute(
        f"INSERT INTO attendance(name,subject,date) VALUES({qm},{qm},{qm})",
        (best_name, subject, today)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "name": best_name,
        "message": "Marked",
        "box": [top, right, bottom, left]
    })


# ===============================
# CHECK DB
# ===============================
@app.route("/check_db")
def check_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT * FROM attendance")
    rows = c.fetchall()

    conn.close()

    return str(rows)


# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    app.run(debug=True) 