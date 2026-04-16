"""Production-ready Smart Attendance System (Flask + browser webcam)."""

from __future__ import annotations

import csv
import os
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from database import (
    attendance_summary,
    delete_user,
    fraud_logs,
    init_db,
    list_users,
    log_fraud,
    mark_attendance,
    recent_logs,
    subject_options,
    subject_wise_summary,
    upsert_user,
)
from recognition import FACE_LIB_AVAILABLE, FaceRecognitionService, RecognitionError

APP_SECRET = os.getenv("APP_SECRET", "change-me-in-production")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ATTENDANCE_CSV = Path("attendance.csv")

app = Flask(__name__)
app.secret_key = APP_SECRET

recognition_service = FaceRecognitionService(threshold=0.6)
init_db()


def login_required(handler: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(handler)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            return jsonify({"success": False, "message": "Forbidden"}), 403
        return handler(*args, **kwargs)

    return wrapper


def json_error(message: str, status: int = 400) -> Any:
    return jsonify({"success": False, "message": message}), status


def append_csv(name: str, user_id: str, subject: str, timestamp: str, confidence: float) -> None:
    exists = ATTENDANCE_CSV.exists()
    with ATTENDANCE_CSV.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if not exists:
            writer.writerow(["name", "user_id", "subject", "timestamp", "confidence"])
        writer.writerow([name, user_id, subject, timestamp, round(confidence, 4)])


@app.get("/login")
def login() -> Any:
    if session.get("authenticated"):
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.post("/login")
def login_post() -> Any:
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session["authenticated"] = True
        session["role"] = "admin"
        session["username"] = username
        return redirect(url_for("dashboard"))

    return render_template("login.html", error="Invalid credentials")


@app.post("/logout")
@login_required
def logout() -> Any:
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
def index() -> Any:
    if session.get("authenticated"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.get("/dashboard")
@login_required
def dashboard() -> Any:
    return render_template(
        "dashboard.html",
        username=session.get("username", "admin"),
        face_lib_available=FACE_LIB_AVAILABLE,
        subjects=subject_options() or ["Mathematics", "Physics", "Chemistry", "Biology", "English"],
        users=recognition_service.list_users(),
    )


@app.get("/api/dashboard-data")
@login_required
def dashboard_data() -> Any:
    try:
        summary = attendance_summary() or []
        by_subject = subject_wise_summary() or []
        logs = recent_logs(limit=100) or []
        fraud = fraud_logs(limit=100) or []
        users = list_users() or []
        return jsonify(
            {
                "success": True,
                "summary": summary,
                "subjects": by_subject,
                "logs": logs,
                "fraud": fraud,
                "users": users,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return json_error(f"Failed to load dashboard data: {exc}", 500)


@app.post("/api/register")
@login_required
def api_register() -> Any:
    payload = request.get_json(silent=True) or {}
    user_id = str(payload.get("user_id", "")).strip()
    name = str(payload.get("name", "")).strip()
    image_data = payload.get("image")

    if not user_id or not name:
        return json_error("user_id and name are required")

    try:
        recognition_service.register_face(user_id=user_id, name=name, image_data=image_data)
        upsert_user(user_id=user_id, name=name)
        return jsonify({"success": True, "message": "User registered successfully"})
    except RecognitionError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return json_error(f"Registration failed: {exc}", 500)


@app.post("/api/recognize")
@login_required
def api_recognize() -> Any:
    payload = request.get_json(silent=True) or {}
    subject = str(payload.get("subject", "")).strip()
    image_data = payload.get("image")

    if not subject:
        return json_error("subject is required")

    try:
        match = recognition_service.match_face(image_data)

        if not match.matched:
            log_fraud(
                "unknown_face",
                f"Unknown face attempt. distance={match.distance:.3f}, confidence={match.confidence:.2f}",
            )
            return json_error("Unknown face. Attendance not marked.", 404)

        result = mark_attendance(
            user_id=match.user_id or "",
            name=match.name or "Unknown",
            subject=subject,
            confidence=match.confidence,
        )

        if result["duplicate"]:
            log_fraud(
                "duplicate_same_day",
                f"Duplicate attendance blocked for subject={subject}, date={result['attendance_date']}",
                user_id=match.user_id,
                name=match.name,
            )
            return json_error("Attendance already marked today for this subject.", 409)

        append_csv(match.name or "Unknown", match.user_id or "", subject, result["timestamp"], match.confidence)
        return jsonify(
            {
                "success": True,
                "message": "Attendance marked successfully",
                "attendance": {
                    "user_id": match.user_id,
                    "name": match.name,
                    "subject": subject,
                    "timestamp": result["timestamp"],
                    "confidence": round(match.confidence, 4),
                },
            }
        )
    except RecognitionError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return json_error(f"Recognition failed: {exc}", 500)


@app.delete("/api/users/<user_id>")
@login_required
def api_delete_user(user_id: str) -> Any:
    try:
        delete_user(user_id)
        recognition_service.delete_user(user_id)
        return jsonify({"success": True, "message": f"Deleted user {user_id}"})
    except Exception as exc:  # noqa: BLE001
        return json_error(f"Delete failed: {exc}", 500)


@app.get("/health")
def health() -> Any:
    return jsonify({"success": True, "face_lib_available": FACE_LIB_AVAILABLE})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
