"""Smart Attendance System Flask app."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

import cv2
import face_recognition
from flask import Flask, jsonify, render_template, request

from database import (
    dashboard_stats,
    has_attendance_in_session,
    init_db,
    log_attendance,
    log_fraud,
    log_unknown_attempt,
    recent_duplicate,
    upsert_user,
)
from recognition import FaceRecognitionService, liveness_check_from_frame

ATTENDANCE_CSV = Path("attendance.csv")
LOW_CONFIDENCE_CUTOFF = 0.5

app = Flask(__name__)
face_service = FaceRecognitionService()
init_db()


def append_attendance_csv(name: str, user_id: str, confidence: float, timestamp: str) -> None:
    file_exists = ATTENDANCE_CSV.exists()
    with ATTENDANCE_CSV.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if not file_exists:
            writer.writerow(["name", "user_id", "timestamp", "confidence"])
        writer.writerow([name, user_id, timestamp, round(confidence, 4)])


def _json_error(message: str, code: int = 400) -> Any:
    return jsonify({"success": False, "message": message}), code


@app.route("/")
def home() -> str:
    data = dashboard_stats()
    return render_template("dashboard.html", **data)


@app.route("/register", methods=["POST"])
def register_user() -> Any:
    payload: Dict[str, Any] = request.get_json(silent=True) or request.form.to_dict()
    user_id = payload.get("user_id", "").strip()
    name = payload.get("name", "").strip()
    image_count = int(payload.get("image_count", 8))

    if not user_id or not name:
        return _json_error("user_id and name are required")

    if image_count < 5 or image_count > 10:
        return _json_error("image_count must be between 5 and 10")

    try:
        images = face_service.capture_registration_images(user_id, name, image_count)
        record = face_service.build_user_encoding(user_id, name, images)
        upsert_user(user_id, name)
    except Exception as exc:  # noqa: BLE001
        return _json_error(f"Registration failed: {exc}", 500)

    return jsonify(
        {
            "success": True,
            "message": "User registered successfully",
            "user": {"user_id": user_id, "name": name, "samples": record["samples"]},
        }
    )


@app.route("/recognize", methods=["POST", "GET"])
def recognize_user() -> Any:
    payload: Dict[str, Any] = request.get_json(silent=True) or request.form.to_dict()
    session_id = payload.get("session_id", "default-session")
    prevent_duplicate = str(payload.get("prevent_duplicate", "true")).lower() == "true"
    require_liveness = str(payload.get("require_liveness", "true")).lower() == "true"

    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        return _json_error("Could not open webcam", 500)

    success, frame = camera.read()
    camera.release()

    if not success:
        return _json_error("Failed to capture frame from webcam", 500)

    if require_liveness and not liveness_check_from_frame(frame):
        log_fraud("liveness_failed", "Liveness check failed. Potential spoofing attempt")
        return _json_error("Liveness check failed", 403)

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb)

    if not locations:
        return _json_error("No face detected in frame")

    encodings = face_recognition.face_encodings(rgb, locations)
    if not encodings:
        return _json_error("No face encodings could be extracted")

    match = face_service.match_face(encodings[0])

    if not match.matched:
        log_unknown_attempt(match.confidence)
        log_fraud("unknown_face", f"Unknown face attempt with confidence={match.confidence:.2f}")
        return _json_error("Unknown face. Attendance not marked", 404)

    if match.confidence < LOW_CONFIDENCE_CUTOFF:
        log_fraud(
            "low_confidence_reject",
            f"Matched user but confidence too low ({match.confidence:.2f})",
            user_id=match.user_id,
            name=match.name,
        )
        return _json_error("Low confidence match rejected", 403)

    if recent_duplicate(match.user_id, minutes=5):
        log_fraud(
            "rapid_repeat",
            "Same user attempted attendance within 5 minutes",
            user_id=match.user_id,
            name=match.name,
        )
        return _json_error("Attendance already marked recently", 409)

    if prevent_duplicate and has_attendance_in_session(match.user_id, session_id):
        log_fraud(
            "duplicate_session",
            f"Duplicate attempt in same session={session_id}",
            user_id=match.user_id,
            name=match.name,
        )
        return _json_error("Duplicate attendance in this session", 409)

    log_attendance(match.user_id, match.name or "Unknown", match.confidence, session_id)

    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).isoformat()
    append_attendance_csv(match.name or "Unknown", match.user_id or "", match.confidence, timestamp)

    return jsonify(
        {
            "success": True,
            "message": "Attendance marked",
            "attendance": {
                "user_id": match.user_id,
                "name": match.name,
                "confidence": round(match.confidence, 4),
                "session_id": session_id,
                "event_id": str(uuid4()),
            },
        }
    )


@app.route("/attendance", methods=["GET"])
def attendance_data() -> Any:
    return jsonify({"success": True, "data": dashboard_stats()})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
