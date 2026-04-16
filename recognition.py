"""Face registration, recognition, and lightweight liveness utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import face_recognition
import numpy as np


@dataclass
class MatchResult:
    """Result from matching a face encoding against known users."""

    matched: bool
    user_id: Optional[str]
    name: Optional[str]
    distance: float
    confidence: float


class FaceRecognitionService:
    """Loads, stores, and matches face encodings."""

    def __init__(self, encodings_file: str = "encodings/face_encodings.json", threshold: float = 0.6) -> None:
        self.encodings_path = Path(encodings_file)
        self.threshold = threshold
        self._data = self._load()

    def _load(self) -> Dict[str, dict]:
        if not self.encodings_path.exists():
            self.encodings_path.parent.mkdir(parents=True, exist_ok=True)
            self.encodings_path.write_text("{}", encoding="utf-8")
            return {}

        with self.encodings_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _save(self) -> None:
        with self.encodings_path.open("w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2)

    def capture_registration_images(
        self,
        user_id: str,
        name: str,
        num_images: int = 8,
        output_dir: str = "dataset",
    ) -> List[Path]:
        """Capture registration images from webcam for one user."""
        user_dir = Path(output_dir) / f"{user_id}_{name.replace(' ', '_')}"
        user_dir.mkdir(parents=True, exist_ok=True)

        camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            raise RuntimeError("Could not open webcam")

        saved_paths: List[Path] = []
        captured = 0

        while captured < num_images:
            success, frame = camera.read()
            if not success:
                continue

            display = frame.copy()
            cv2.putText(
                display,
                f"Registration {captured + 1}/{num_images} - press SPACE to capture",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
            )
            cv2.imshow("Register Face", display)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break

            if key == ord(" "):
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                locations = face_recognition.face_locations(rgb)
                if len(locations) != 1:
                    continue

                image_path = user_dir / f"img_{captured + 1}.jpg"
                cv2.imwrite(str(image_path), frame)
                saved_paths.append(image_path)
                captured += 1

        camera.release()
        cv2.destroyAllWindows()
        return saved_paths

    def build_user_encoding(self, user_id: str, name: str, image_paths: List[Path]) -> dict:
        """Aggregate encodings from registration images and persist one profile."""
        encodings = []

        for path in image_paths:
            image = face_recognition.load_image_file(str(path))
            image_encodings = face_recognition.face_encodings(image)
            if image_encodings:
                encodings.append(image_encodings[0])

        if not encodings:
            raise ValueError("No valid face encodings extracted for user")

        average_encoding = np.mean(np.array(encodings), axis=0)
        user_record = {
            "user_id": user_id,
            "name": name,
            "encoding": average_encoding.tolist(),
            "samples": len(encodings),
        }

        self._data[user_id] = user_record
        self._save()
        return user_record

    def known_matrix(self) -> Tuple[np.ndarray, List[str], List[str]]:
        """Return matrix of known encodings and associated metadata."""
        if not self._data:
            return np.array([]), [], []

        user_ids = list(self._data.keys())
        names = [self._data[uid]["name"] for uid in user_ids]
        matrix = np.array([self._data[uid]["encoding"] for uid in user_ids])
        return matrix, user_ids, names

    def match_face(self, face_encoding: np.ndarray) -> MatchResult:
        """Match one face encoding against known encodings."""
        matrix, user_ids, names = self.known_matrix()
        if matrix.size == 0:
            return MatchResult(False, None, None, distance=1.0, confidence=0.0)

        distances = face_recognition.face_distance(matrix, face_encoding)
        best_idx = int(np.argmin(distances))
        best_distance = float(distances[best_idx])
        confidence = float(max(0.0, min(1.0, 1.0 - best_distance)))

        if best_distance <= self.threshold:
            return MatchResult(True, user_ids[best_idx], names[best_idx], best_distance, confidence)

        return MatchResult(False, None, None, best_distance, confidence)


def eye_aspect_ratio(eye_points: List[Tuple[int, int]]) -> float:
    """Compute Eye Aspect Ratio (EAR) from 6 eye landmarks."""

    def dist(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.linalg.norm(a - b))

    points = np.array(eye_points, dtype="float")
    vertical_1 = dist(points[1], points[5])
    vertical_2 = dist(points[2], points[4])
    horizontal = dist(points[0], points[3])

    if horizontal == 0:
        return 0.0

    return (vertical_1 + vertical_2) / (2.0 * horizontal)


def liveness_check_from_frame(frame: np.ndarray, ear_threshold: float = 0.2) -> bool:
    """Simple liveness check: eye openness/movement heuristic from one frame.

    This is intentionally lightweight and should be considered a baseline.
    """
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    landmarks = face_recognition.face_landmarks(rgb)

    if not landmarks:
        return False

    eyes_open = False
    for face_landmarks in landmarks:
        if "left_eye" in face_landmarks and "right_eye" in face_landmarks:
            left_ear = eye_aspect_ratio(face_landmarks["left_eye"])
            right_ear = eye_aspect_ratio(face_landmarks["right_eye"])
            avg_ear = (left_ear + right_ear) / 2.0
            if avg_ear > ear_threshold:
                eyes_open = True

    return eyes_open
