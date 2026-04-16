# Smart Attendance System (Production-Ready)

A full-stack, browser-webcam smart attendance system with face registration, face recognition, duplicate prevention, subject-wise tracking, admin authentication, and a premium glassmorphism dashboard.

## Highlights

- Admin login + session-based role protection
- Browser camera via `getUserMedia` (**no `cv2.imshow` popups**)
- Face registration from base64 image
- Face recognition with Euclidean threshold `0.6`
- Attendance logging in SQLite + CSV
- Duplicate prevention per **user + subject + day**
- Dynamic attendance calculations:
  - overall (`present days / total class days`)
  - subject-wise percentages
- Fraud logging for unknown faces + duplicate attempts
- Apple-like UI/UX (glass cards, dark gradients, smooth hover transitions)

## Project Structure

```text
smart-attendance-system/
├── app.py
├── database.py
├── recognition.py
├── requirements.txt
├── attendance.csv               # auto-created
├── attendance.db                # auto-created
├── encodings/
│   ├── .gitkeep
│   └── face_encodings.json      # auto-created
├── dataset/
│   └── .gitkeep
└── templates/
    ├── login.html
    └── dashboard.html
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open in browser: `http://localhost:5000`

## Default Admin Login

- Username: `admin`
- Password: `admin123`

> Change these for production with environment variables:

```bash
export ADMIN_USERNAME='your-admin'
export ADMIN_PASSWORD='strong-password'
export APP_SECRET='very-strong-secret'
```

## API Endpoints (Admin session required)

- `POST /api/register`
  - JSON: `{ "user_id": "STU-001", "name": "Alice", "image": "data:image/jpeg;base64,..." }`
- `POST /api/recognize`
  - JSON: `{ "subject": "Mathematics", "image": "data:image/jpeg;base64,..." }`
- `GET /api/dashboard-data`
- `DELETE /api/users/<user_id>`

## Stability Design

- Safe fallbacks for empty DB (`[]` summaries)
- Graceful error messages for:
  - missing face library
  - no face / multiple faces / unknown face
- Never renders blank dashboard on empty records

## Production Notes

- Use HTTPS and secure cookies
- Replace default credentials immediately
- Add CSRF protection and stricter auth policies
- Consider encrypting face embeddings at rest
