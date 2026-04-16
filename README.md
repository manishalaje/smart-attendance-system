# Smart Attendance System (Face Recognition + Fraud Detection)

Production-style mini project that uses webcam-based face recognition for attendance, with fraud/proxy detection and a Flask dashboard.

## Features

- **Face registration** (5–10 webcam captures per user) and encoding generation via `face_recognition`
- **Realtime face recognition** with configurable threshold (`0.6` default)
- **Attendance logging** to both:
  - `attendance.csv`
  - SQLite (`attendance.db`)
- **Fraud detection**:
  - Rapid repeat attendance attempts (same user within 5 minutes)
  - Unknown face attempts
  - Low-confidence match rejection
  - Duplicate attendance in same session prevention
- **Basic liveness check** based on eye landmarks (EAR heuristic)
- **Dashboard UI** with:
  - Total attendance per user
  - Recent attendance logs
  - Fraud alerts
- **REST APIs**:
  - `POST /register`
  - `POST /recognize`
  - `GET /attendance`

## Project Structure

```text
smart-attendance-system/
├── app.py
├── recognition.py
├── database.py
├── requirements.txt
├── attendance.csv                # Generated automatically
├── attendance.db                 # Generated automatically
├── encodings/
│   ├── .gitkeep
│   └── face_encodings.json       # Generated automatically
├── dataset/
│   └── .gitkeep
└── templates/
    └── dashboard.html
```

## Setup

1. Create a Python virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the app:

   ```bash
   python app.py
   ```

4. Open dashboard:

   - `http://localhost:5000/`

## API Usage

### 1) Register User

Captures webcam images interactively. Press **SPACE** to capture each frame; press **q** to cancel.

```bash
curl -X POST http://localhost:5000/register \
  -H "Content-Type: application/json" \
  -d '{"user_id":"E001","name":"Alice","image_count":8}'
```

### 2) Recognize / Mark Attendance

```bash
curl -X POST http://localhost:5000/recognize \
  -H "Content-Type: application/json" \
  -d '{"session_id":"morning-lecture","prevent_duplicate":true,"require_liveness":true}'
```

### 3) Fetch Attendance Data

```bash
curl http://localhost:5000/attendance
```

## Fraud Logic Notes

- **Rapid repeat**: attendance attempt blocked if already marked in last 5 minutes.
- **Unknown face**: logged to `unknown_attempts` and `fraud_alerts`.
- **Low confidence**: rejected when confidence `< 0.5`.
- **Same session duplicate**: blocked if user already marked within provided `session_id`.

## Production Hardening Suggestions

- Add JWT auth and role-based access.
- Move webcam operations to edge client and send frames securely.
- Replace heuristic liveness with model-based anti-spoofing.
- Add retries, async workers, and monitoring.
- Encrypt face embeddings at rest.
