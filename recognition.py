"""Face encoding and matching utilities for browser-captured images."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

try:
    import face_recognition

    FACE_LIB_AVAILABLE = True
except Exception:  # noqa: BLE001
    face_recognition = None
    FACE_LIB_AVAILABLE = False


@dataclass
class FaceMatch:
    matched: bool
    user_id: Optional[str]
    name: Optional[str]
    distance: float
    confidence: float


class RecognitionError(Exception):
    """User-facing recognition error."""


class FaceRecognitionService:
    def __init__(self, encodings_file: str = "encodings/face_encodings.json", threshold: float = 0.6) -> None:
        self.threshold = threshold
        self.encodings_path = Path(encodings_file)
        self.encodings_path.parent.mkdir(parents=True, exist_ok=True)
        self._encodings = self._load_encodings()

    def _ensure_lib(self) -> None:
        if not FACE_LIB_AVAILABLE:
            raise RecognitionError(
                "face_recognition/dlib is not installed. Install dependencies and restart the app."
            )

    def _load_encodings(self) -> Dict[str, dict]:
        if not self.encodings_path.exists():
            self.encodings_path.write_text("{}", encoding="utf-8")
            return {}

        try:
            return json.loads(self.encodings_path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            return {}

    def _save_encodings(self) -> None:
        self.encodings_path.write_text(json.dumps(self._encodings, indent=2), encoding="utf-8")

    def list_users(self) -> list[dict]:
        return [
            {"user_id": u["user_id"], "name": u["name"], "samples": u.get("samples", 1)}
            for u in self._encodings.values()
        ]

    def delete_user(self, user_id: str) -> None:
        if user_id in self._encodings:
            del self._encodings[user_id]
            self._save_encodings()

    @staticmethod
    def decode_base64_image(image_data: str) -> np.ndarray:
        if not image_data:
            raise RecognitionError("Image payload is missing")

        # Supports both data URL and raw base64
        payload = image_data.split(",", 1)[1] if image_data.startswith("data:image") else image_data

        try:
            image_bytes = base64.b64decode(payload)
            pil_image = Image.open(BytesIO(image_bytes)).convert("RGB")
            rgb = np.array(pil_image)
            # face_recognition expects RGB; keep RGB matrix and also return a BGR conversion when needed.
            return rgb
        except Exception as exc:  # noqa: BLE001
            raise RecognitionError(f"Invalid image data: {exc}") from exc

    def encoding_from_base64(self, image_data: str) -> np.ndarray:
        self._ensure_lib()
        rgb = self.decode_base64_image(image_data)
        locations = face_recognition.face_locations(rgb)

        if len(locations) == 0:
            raise RecognitionError("No face detected. Please align your face and try again.")
        if len(locations) > 1:
            raise RecognitionError("Multiple faces detected. Only one face is allowed.")

        encodings = face_recognition.face_encodings(rgb, known_face_locations=locations)
        if not encodings:
            raise RecognitionError("Could not encode face. Please improve lighting and retry.")

        return encodings[0]

    def register_face(self, user_id: str, name: str, image_data: str) -> dict:
        encoding = self.encoding_from_base64(image_data)
        self._encodings[user_id] = {
            "user_id": user_id,
            "name": name,
            "encoding": encoding.tolist(),
            "samples": 1,
        }
        self._save_encodings()
        return self._encodings[user_id]

    def match_face(self, image_data: str) -> FaceMatch:
        self._ensure_lib()
        face_encoding = self.encoding_from_base64(image_data)

        if not self._encodings:
            return FaceMatch(False, None, None, distance=1.0, confidence=0.0)

        user_ids = list(self._encodings.keys())
        names = [self._encodings[uid]["name"] for uid in user_ids]
        known = np.array([self._encodings[uid]["encoding"] for uid in user_ids])

        distances = face_recognition.face_distance(known, face_encoding)
        best_idx = int(np.argmin(distances))
        best_distance = float(distances[best_idx])
        confidence = float(max(0.0, min(1.0, 1.0 - best_distance)))

        if best_distance <= self.threshold:
            return FaceMatch(True, user_ids[best_idx], names[best_idx], best_distance, confidence)

        return FaceMatch(False, None, None, best_distance, confidence)

    def debug_preview_bgr(self, image_data: str) -> np.ndarray:
        """Optional helper for future diagnostics without cv2.imshow."""
        rgb = self.decode_base64_image(image_data)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
