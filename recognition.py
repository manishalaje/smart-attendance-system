import os
import json
import numpy as np
import face_recognition

ENCODING_FILE = "encodings/encodings.json"


class MatchResult:
    def __init__(self, matched=False, name=None, confidence=0):
        self.matched = matched
        self.name = name
        self.confidence = confidence


class FaceRecognitionService:

    def __init__(self):
        self.known_encodings = []
        self.known_names = []

        os.makedirs("encodings", exist_ok=True)
        self.load()

    def load(self):
        if not os.path.exists(ENCODING_FILE):
            return

        with open(ENCODING_FILE, "r") as f:
            data = json.load(f)

        self.known_encodings = [np.array(e) for e in data.get("encodings", [])]
        self.known_names = data.get("names", [])

    def save(self):
        with open(ENCODING_FILE, "w") as f:
            json.dump({
                "encodings": [e.tolist() for e in self.known_encodings],
                "names": self.known_names
            }, f)

    def register_face(self, encoding, name):
        # 🔥 CHECK DUPLICATE FACE
        if self.known_encodings:
            distances = face_recognition.face_distance(self.known_encodings, encoding)
            if min(distances) < 0.45:
                return False, "Face already registered"

        self.known_encodings.append(encoding)
        self.known_names.append(name)
        self.save()

        return True, "Registered successfully"

    def match_face(self, encoding):
        if not self.known_encodings:
            return MatchResult(False)

        distances = face_recognition.face_distance(self.known_encodings, encoding)
        best = np.argmin(distances)

        confidence = 1 - distances[best]

        if distances[best] < 0.5:
            return MatchResult(True, self.known_names[best], confidence)

        return MatchResult(False)