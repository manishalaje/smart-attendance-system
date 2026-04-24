from flask import Flask, render_template, request, jsonify, redirect, session
import os
import base64
import numpy as np
import io
from datetime import datetime
from PIL import Image
import psycopg2
from psycopg2 import Binary

# ===============================
# 🔥 TOGGLE MODE
# ===============================
USE_AI = os.getenv("USE_AI", "True").lower() == "true"

# ===============================
# 🔥 APP CONFIG
# ===============================
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.getenv("SECRET_KEY", "secret123")

# ===============================
# 🔥 FACE IMPORT
# ===============================
FACE_AVAILABLE = False

try:
    if USE_AI:
        import face_recognition
        FACE_AVAILABLE = True
except:
    print("face_recognition not available (OK for server)")

# ===============================
# 🔥 POSTGRES CONFIG
# ===============================
DATABASE_URL = os.getenv("DATABASE_URL")

# ===============================
# ---------- DB ----------
# ===============================
def get_conn():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE,
        encoding BYTEA
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS attendance(
        id SERIAL PRIMARY KEY,
        name TEXT,
        subject TEXT,
        date DATE
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS accounts(
        id SERIAL PRIMARY KEY,
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

    c.execute("SELECT * FROM accounts WHERE username=%s", ('admin',))
    exists = c.fetchone()

    if not exists:
        c.execute(
            "INSERT INTO accounts(username,password,role) VALUES(%s,%s,%s)",
            ('admin', 'admin123', 'admin')
        )

    conn.commit()
    conn.close()


init_db()
create_admin()

# ===============================
# ---------- IMAGE ----------
# ===============================
def decode_image(data):
    data = data.split(",")[1]
    img_bytes = base64.b64decode(data)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    return np.array(img)


# ===============================
# 🔥 FACE ENCODING
# ===============================
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
# ---------- SIGNUP ----------
# ===============================
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = get_conn()
        c = conn.cursor()

        c.execute("SELECT * FROM accounts WHERE username=%s", (u,))
        exists = c.fetchone()

        if exists:
            conn.close()
            return "User already exists"

        c.execute(
            "INSERT INTO accounts(username,password,role) VALUES(%s,%s,%s)",
            (u, p, "student")
        )

        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("signup.html")


# ===============================
# ---------- LOGIN ----------
# ===============================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = get_conn()
        c = conn.cursor()

        c.execute(
            "SELECT * FROM accounts WHERE username=%s AND password=%s",
            (u, p)
        )

        user = c.fetchone()
        conn.close()

        if user:
            session["user"] = u
            session["role"] = user[3]

            if user[3] == "admin":
                return redirect("/")
            else:
                return redirect("/student")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ===============================
# 🔥 ADMIN DASHBOARD
# ===============================
@app.route("/")
def home():
    if "user" not in session or session.get("role") != "admin":
        return redirect("/login")

    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT name,subject,date FROM attendance ORDER BY id DESC")
    logs = c.fetchall()

    subjects = ["AI", "Math", "DBMS"]

    c.execute("SELECT COUNT(*) FROM users")
    total_students = c.fetchone()[0]

    today = datetime.now().date()

    c.execute("""
        SELECT COUNT(DISTINCT name)
        FROM attendance
        WHERE date=%s
    """, (today,))
    present_total = c.fetchone()[0]

    summary = []
    subject_counts = []

    for s in subjects:
        c.execute("""
        SELECT COUNT(DISTINCT name)
        FROM attendance
        WHERE subject=%s AND date=%s
        """, (s, today))

        present = c.fetchone()[0]

        percentage = int((present / total_students) * 100) if total_students > 0 else 0
        percentage = min(percentage, 100)

        subject_counts.append(present)

        summary.append({
            "subject": s,
            "present": present,
            "percentage": percentage
        })

    # 🔥 TOP STUDENTS
    c.execute("SELECT COUNT(DISTINCT date) FROM attendance")
    total_classes = c.fetchone()[0]

    total_subjects = len(subjects)

    c.execute("""
        SELECT name, COUNT(*) as total
        FROM attendance
        GROUP BY name
        ORDER BY total DESC
        LIMIT 3
    """)

    rows = c.fetchall()

    top_students = []

    for row in rows:
        name = row[0]
        total = row[1]

        total_possible = max(total_classes * total_subjects, 1)

        percent = int((total / total_possible) * 100)
        percent = min(percent, 100)

        top_students.append({
            "name": name,
            "percentage": percent
        })

    conn.close()

    absent = max(0, total_students - present_total)

    return render_template(
        "dashboard.html",
        logs=logs,
        summary=summary,
        subjects=subjects,
        subject_counts=subject_counts,
        total_students=total_students,
        present_total=present_total,
        absent=absent,
        top_students=top_students
    )


# ===============================
# ---------- STUDENT ----------
# ===============================
@app.route("/student")
def student_page():
    if "user" not in session or session.get("role") != "student":
        return redirect("/login")

    return render_template("student.html")


# ===============================
# ---------- STUDENT DASHBOARD ----------
# ===============================
@app.route("/student_dashboard")
def student_dashboard():
    if "user" not in session:
        return jsonify({"error": "login required"})

    name = session["user"]

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        SELECT subject, date
        FROM attendance
        WHERE name=%s
    """, (name,))

    logs = c.fetchall()

    total = len(logs)

    unique_days = len(set([str(l[1]) for l in logs]))
    total_possible = max(unique_days * 3, 1)

    percentage = int((total / total_possible) * 100) if total else 0
    percentage = min(percentage, 100)

    subjects_list = ["AI", "Math", "DBMS"]
    subject_data = []

    for sub in subjects_list:
        count = sum(1 for l in logs if l[0] == sub)

        percent_sub = int((count / total) * 100) if total > 0 else 0

        subject_data.append({
            "subject": sub,
            "percentage": percent_sub
        })

    conn.close()

    return jsonify({
        "percentage": percentage,
        "subjects": subject_data,
        "logs": [{"subject": l[0], "date": str(l[1])} for l in logs]
    })


# ===============================
# ---------- LIVE DATA ----------
# ===============================
@app.route("/live_data")
def live_data():
    conn = get_conn()
    c = conn.cursor()

    subjects = ["AI", "Math", "DBMS"]
    counts = []

    for s in subjects:
        c.execute("""
            SELECT COUNT(DISTINCT name)
            FROM attendance
            WHERE subject=%s
        """, (s,))

        present = c.fetchone()[0]
        counts.append(present)

    conn.close()

    return jsonify({
        "subjects": subjects,
        "counts": counts
    })


# ===============================
# ---------- REGISTER ----------
# ===============================
@app.route("/register_image", methods=["POST"])
def register():
    if not USE_AI:
        return jsonify({"message": "Registered (Demo Mode)"})

    data = request.json
    name = data.get("name", "").strip()

    if not name:
        return jsonify({"message": "Name required"})

    img = decode_image(data["image"])
    res = get_encoding(img)

    if not res:
        return jsonify({"message": "No face detected"})

    enc, _ = res

    conn = get_conn()
    c = conn.cursor()

    c.execute("DELETE FROM users WHERE name=%s", (name,))
    c.execute(
        "INSERT INTO users(name,encoding) VALUES(%s,%s)",
        (name, Binary(enc.tobytes()))
    )

    conn.commit()
    conn.close()

    return jsonify({"message": "Registered successfully"})


# ===============================
# ---------- RECOGNIZE ----------
# ===============================
@app.route("/recognize_image", methods=["POST"])
def recognize():
    subject = request.json.get("subject")

    if not USE_AI:
        name = "Demo User"
        today = datetime.now().date()

        conn = get_conn()
        c = conn.cursor()

        c.execute("""
            SELECT * FROM attendance
            WHERE name=%s AND subject=%s AND date=%s
        """, (name, subject, today))

        exists = c.fetchone()

        if not exists:
            c.execute(
                "INSERT INTO attendance(name,subject,date) VALUES(%s,%s,%s)",
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

    data = request.json
    img = decode_image(data["image"])
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
        uname = row[0]
        db = np.frombuffer(row[1], dtype=np.float64)

        dist = np.linalg.norm(enc - db)

        if dist < best:
            best = dist
            best_name = uname

    if best > 0.5:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Unknown",
            "box": [top, right, bottom, left]
        })

    today = datetime.now().date()

    c.execute("""
        SELECT * FROM attendance
        WHERE name=%s AND subject=%s AND date=%s
    """, (best_name, subject, today))

    exists = c.fetchone()

    if exists:
        conn.close()
        return jsonify({
            "success": True,
            "name": best_name,
            "message": "Already marked",
            "box": [top, right, bottom, left]
        })

    c.execute(
        "INSERT INTO attendance(name,subject,date) VALUES(%s,%s,%s)",
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
# ---------- REMOTE ----------
# ===============================
@app.route("/mark_remote", methods=["POST"])
def mark_remote():
    data = request.json

    name = data.get("name", "").strip()
    subject = data.get("subject")

    if not name:
        return jsonify({"message": "Name required"})

    today = datetime.now().date()

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        SELECT * FROM attendance
        WHERE name=%s AND subject=%s AND date=%s
    """, (name, subject, today))

    exists = c.fetchone()

    if not exists:
        c.execute(
            "INSERT INTO attendance(name,subject,date) VALUES(%s,%s,%s)",
            (name, subject, today)
        )
        conn.commit()

    conn.close()

    return jsonify({"message": "Marked online"})


@app.route("/register_remote", methods=["POST"])
def register_remote():
    data = request.json

    name = data["name"]
    enc = np.array(data["encoding"], dtype=np.float64)

    conn = get_conn()
    c = conn.cursor()

    c.execute("DELETE FROM users WHERE name=%s", (name,))
    c.execute(
        "INSERT INTO users(name,encoding) VALUES(%s,%s)",
        (name, Binary(enc.tobytes()))
    )

    conn.commit()
    conn.close()

    return jsonify({"message": "User synced"})


# ===============================
# ---------- CHECK DB ----------
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
# ---------- RUN ----------
# ===============================
if __name__ == "__main__":
    app.run(debug=True)