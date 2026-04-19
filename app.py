from flask import Flask, render_template, request, jsonify, redirect, session
import sqlite3, base64, numpy as np, io
from datetime import datetime
from PIL import Image

# ===============================
# 🔥 TOGGLE MODE
# ===============================
USE_AI = False   # 👉 True = LOCAL AI, False = DEPLOY MODE

# import only if needed
if USE_AI:
    import face_recognition


app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = "secret123"

DB = "attendance.db"


# ---------- DB ----------
def get_conn():
    return sqlite3.connect(DB)


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT UNIQUE, encoding BLOB)")
    c.execute("CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY, name TEXT, subject TEXT, date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT)")

    conn.commit()
    conn.close()

init_db()


def create_admin():
    conn = get_conn()
    c = conn.cursor()

    if not c.execute("SELECT * FROM accounts WHERE username='admin'").fetchone():
        c.execute("INSERT INTO accounts VALUES(NULL,'admin','admin123','admin')")

    conn.commit()
    conn.close()

create_admin()


# ---------- IMAGE ----------
def decode_image(data):
    data = data.split(",")[1]
    img_bytes = base64.b64decode(data)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    return np.array(img)


# ===============================
# 🔥 FACE ENCODING (FULL KEPT)
# ===============================
def get_encoding(img):

    # ---------- DEMO MODE ----------
    if not USE_AI:
        return None

    # ---------- REAL AI MODE ----------
    img = np.ascontiguousarray(img, dtype=np.uint8)
    loc = face_recognition.face_locations(img)

    if not loc:
        return None

    enc = face_recognition.face_encodings(img, loc)
    return enc[0], loc[0]


# ---------- SIGNUP ----------
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = get_conn()
        c = conn.cursor()

        exists = c.execute("SELECT * FROM accounts WHERE username=?", (u,)).fetchone()

        if exists:
            return "User already exists"

        c.execute("INSERT INTO accounts VALUES(NULL,?,?,?)", (u,p,"student"))

        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("signup.html")


# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = get_conn()
        c = conn.cursor()

        user = c.execute(
            "SELECT * FROM accounts WHERE username=? AND password=?",
            (u, p)
        ).fetchone()

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


# ---------- ADMIN DASHBOARD ----------
@app.route("/")
def home():
    if "user" not in session or session.get("role") != "admin":
        return redirect("/login")

    conn = get_conn()
    c = conn.cursor()

    logs = c.execute(
        "SELECT name,subject,date FROM attendance ORDER BY id DESC"
    ).fetchall()

    subjects = ["AI", "Math", "DBMS"]

    total_students = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    present_total = c.execute("""
        SELECT COUNT(DISTINCT name)
        FROM attendance
        WHERE date=?
    """, (datetime.now().strftime("%Y-%m-%d"),)).fetchone()[0]

    summary = []
    subject_counts = []

    for s in subjects:
        present = c.execute("""
            SELECT COUNT(DISTINCT name)
            FROM attendance WHERE subject=?
        """, (s,)).fetchone()[0]

        percentage = int((present / total_students) * 100) if total_students else 0

        subject_counts.append(present)

        summary.append({
            "subject": s,
            "present": present,
            "percentage": percentage
        })

    conn.close()

    return render_template("dashboard.html",
        logs=logs,
        summary=summary,
        subjects=subjects,
        subject_counts=subject_counts,
        total_students=total_students,
        present_total=present_total
    )


# ---------- STUDENT ----------
@app.route("/student")
def student_page():
    if "user" not in session or session.get("role") != "student":
        return redirect("/login")

    return render_template("student.html")


# ---------- STUDENT DASHBOARD ----------
@app.route("/student_dashboard")
def student_dashboard():

    if "user" not in session:
        return jsonify({"error": "login required"})

    name = session["user"]

    conn = get_conn()
    c = conn.cursor()

    logs = c.execute("""
        SELECT subject, date
        FROM attendance
        WHERE name=?
    """, (name,)).fetchall()

    total = len(logs)
    percentage = 100 if total > 0 else 0

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
        "logs": [{"subject": l[0], "date": l[1]} for l in logs]
    })


# ---------- LIVE DATA ----------
@app.route("/live_data")
def live_data():
    conn = get_conn()
    c = conn.cursor()

    subjects = ["AI", "Math", "DBMS"]
    counts = []

    for s in subjects:
        present = c.execute("""
            SELECT COUNT(DISTINCT name)
            FROM attendance WHERE subject=?
        """, (s,)).fetchone()[0]

        counts.append(present)

    conn.close()

    return jsonify({
        "subjects": subjects,
        "counts": counts
    })


# ===============================
# 🔥 REGISTER (TOGGLE SAFE)
# ===============================
@app.route("/register_image", methods=["POST"])
def register():

    if not USE_AI:
        return jsonify({"message": "Registered (Demo Mode)"})

    data = request.json
    img = decode_image(data["image"])
    res = get_encoding(img)

    if not res:
        return jsonify({"message": "No face detected"})

    enc, _ = res

    conn = get_conn()
    c = conn.cursor()

    c.execute("DELETE FROM users WHERE name=?", (data["name"],))
    c.execute("INSERT INTO users VALUES(NULL,?,?)",
              (data["name"], enc.tobytes()))

    conn.commit()
    conn.close()

    return jsonify({"message": "Registered successfully"})


# ===============================
# 🔥 RECOGNIZE (TOGGLE SAFE)
# ===============================
@app.route("/recognize_image", methods=["POST"])
def recognize():

    subject = request.json.get("subject")

    # ---------- DEMO ----------
    if not USE_AI:
        name = "Demo User"
        today = datetime.now().strftime("%Y-%m-%d")

        conn = get_conn()
        c = conn.cursor()

        exists = c.execute("""
            SELECT * FROM attendance
            WHERE name=? AND subject=? AND date=?
        """, (name, subject, today)).fetchone()

        if not exists:
            c.execute("INSERT INTO attendance VALUES(NULL,?,?,?)",
                      (name, subject, today))
            conn.commit()

        conn.close()

        return jsonify({
            "success": True,
            "name": name,
            "message": "Marked (Demo Mode)",
            "box": None
        })

    # ---------- REAL AI ----------
    data = request.json
    img = decode_image(data["image"])
    res = get_encoding(img)

    if not res:
        return jsonify({"success": False, "message": "No face", "box": None})

    enc, (top, right, bottom, left) = res

    conn = get_conn()
    c = conn.cursor()

    users = c.execute("SELECT name,encoding FROM users").fetchall()

    best_name = None
    best = 999

    for name, db in users:
        db = np.frombuffer(db, dtype=np.float64)
        dist = np.linalg.norm(enc - db)

        if dist < best:
            best = dist
            best_name = name

    if best > 0.5:
        return jsonify({
            "success": False,
            "message": "Unknown",
            "box": [top, right, bottom, left]
        })

    today = datetime.now().strftime("%Y-%m-%d")

    exists = c.execute("""
        SELECT * FROM attendance
        WHERE name=? AND subject=? AND date=?
    """, (best_name, subject, today)).fetchone()

    if exists:
        return jsonify({
            "success": True,
            "name": best_name,
            "message": "Already marked",
            "box": [top, right, bottom, left]
        })

    c.execute("INSERT INTO attendance VALUES(NULL,?,?,?)",
              (best_name, subject, today))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "name": best_name,
        "message": "Marked",
        "box": [top, right, bottom, left]
    })


# ---------- RUN ----------
if __name__ == "__main__":
    app.run(debug=True)