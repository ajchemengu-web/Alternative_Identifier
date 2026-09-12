import os
import sqlite3
from datetime import datetime

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from src.services.liveness_service import check_liveness


# ============================================================
# PATHS
# ============================================================

DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)

STUDENT_EMBEDDINGS_FOLDER = os.path.join(
    "data",
    "embeddings"
)

GUEST_EMBEDDINGS_FOLDER = os.path.join(
    "data",
    "guests",
    "embeddings"
)

MATCH_THRESHOLD = 0.50

CACHE_REFRESH_INTERVAL = 10


# ============================================================
# LOAD AI MODEL
# ============================================================

print("Loading Face Recognition AI...")

app = FaceAnalysis(
    name="buffalo_l",
    providers=["CPUExecutionProvider"]
)

app.prepare(
    ctx_id=0,
    det_size=(640, 640)
)

print("Face Recognition AI ready!")


# ============================================================
# DATABASE
# ============================================================

def get_connection():

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# IDENTITY CACHE
# ============================================================

class IdentityCache:

    def __init__(self):

        self.students = []
        self.guests = []

        self.last_refresh = 0

        self.refresh()


    # ========================================================
    # LOAD STUDENTS
    # ========================================================

    def load_students(self):

        students = []

        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                student_id,
                full_name,
                admission_number,
                hostel,
                room,
                embedding_file
            FROM students
        """)

        rows = cursor.fetchall()

        connection.close()

        for student in rows:

            embedding_path = os.path.join(
                STUDENT_EMBEDDINGS_FOLDER,
                student["embedding_file"]
            )

            if not os.path.exists(embedding_path):

                print(
                    "[IDENTITY CACHE] "
                    f"Embedding missing: "
                    f"{embedding_path}"
                )

                continue

            try:

                embedding = np.load(
                    embedding_path
                )

                embedding = embedding.astype(
                    np.float32
                )

                norm = np.linalg.norm(
                    embedding
                )

                if norm == 0:

                    print(
                        "[IDENTITY CACHE] "
                        f"Invalid embedding: "
                        f"{embedding_path}"
                    )

                    continue

                embedding = embedding / norm

                students.append({

                    "student_id":
                        student["student_id"],

                    "full_name":
                        student["full_name"],

                    "admission_number":
                        student["admission_number"],

                    "hostel":
                        student["hostel"],

                    "room":
                        student["room"],

                    "embedding":
                        embedding
                })

            except Exception as error:

                print(
                    "[IDENTITY CACHE] "
                    f"Failed to load "
                    f"{embedding_path}: {error}"
                )

        return students


    # ========================================================
    # LOAD ACTIVE GUESTS
    # ========================================================

    def load_active_guests(self):

        guests = []

        connection = get_connection()
        cursor = connection.cursor()

        # Your current guest system stores embedding_file.
        # We therefore select it directly.

        cursor.execute("""
            SELECT
                guest_id,
                embedding_file,
                expires_at
            FROM guests
            WHERE status = ?
        """, ("AG",))

        rows = cursor.fetchall()

        connection.close()

        now = datetime.now()

        for guest in rows:

            if not guest["expires_at"]:
                continue

            try:

                expires_at = datetime.fromisoformat(
                    guest["expires_at"]
                )

            except ValueError:

                continue

            # Ignore expired guests
            if now >= expires_at:
                continue

            embedding_path = os.path.join(
                GUEST_EMBEDDINGS_FOLDER,
                guest["embedding_file"]
            )

            if not os.path.exists(
                embedding_path
            ):

                print(
                    "[IDENTITY CACHE] "
                    f"Guest embedding missing: "
                    f"{embedding_path}"
                )

                continue

            try:

                embedding = np.load(
                    embedding_path
                )

                embedding = embedding.astype(
                    np.float32
                )

                norm = np.linalg.norm(
                    embedding
                )

                if norm == 0:
                    continue

                embedding = embedding / norm

                guests.append({

                    "guest_id":
                        guest["guest_id"],

                    "expires_at":
                        expires_at,

                    "embedding":
                        embedding
                })

            except Exception as error:

                print(
                    "[IDENTITY CACHE] "
                    f"Guest embedding error: "
                    f"{error}"
                )

        return guests


    # ========================================================
    # REFRESH CACHE
    # ========================================================

    def refresh(self):

        print(
            "\n[IDENTITY CACHE] "
            "Refreshing identities..."
        )

        self.students = (
            self.load_students()
        )

        self.guests = (
            self.load_active_guests()
        )

        self.last_refresh = (
            __import__("time").time()
        )

        print(
            "[IDENTITY CACHE] "
            f"Students loaded: "
            f"{len(self.students)}"
        )

        print(
            "[IDENTITY CACHE] "
            f"Guests loaded: "
            f"{len(self.guests)}"
        )


    # ========================================================
    # REFRESH WHEN NEEDED
    # ========================================================

    def refresh_if_needed(self):

        import time

        elapsed = (
            time.time()
            - self.last_refresh
        )

        if elapsed >= CACHE_REFRESH_INTERVAL:

            self.refresh()


# ============================================================
# GLOBAL CACHE
# ============================================================

identity_cache = IdentityCache()


# ============================================================
# FIND BEST MATCH
# ============================================================

def find_best_match(
    face_embedding,
    identities
):

    if not identities:

        return None, 0.0

    face_embedding = (
        face_embedding.astype(
            np.float32
        )
    )

    norm = np.linalg.norm(
        face_embedding
    )

    if norm == 0:

        return None, 0.0

    face_embedding = (
        face_embedding / norm
    )

    best_match = None
    best_score = -1.0

    for identity in identities:

        score = float(
            np.dot(
                face_embedding,
                identity["embedding"]
            )
        )

        if score > best_score:

            best_score = score
            best_match = identity

    if best_score >= MATCH_THRESHOLD:

        return best_match, best_score

    return None, best_score


# ============================================================
# RECOGNIZE EMBEDDING
# ============================================================

def recognize_embedding(face_embedding):

    identity_cache.refresh_if_needed()

    embedding = (
        face_embedding /
        np.linalg.norm(face_embedding)
    )


    # ========================================================
    # STUDENTS
    # ========================================================

    student_match, student_score = (
        find_best_match(
            embedding,
            identity_cache.students
        )
    )

    if student_match is not None:

        return {

            "status": "STUDENT",

            "student_id":
                student_match["student_id"],

            "full_name":
                student_match["full_name"],

            "admission_number":
                student_match["admission_number"],

            "hostel":
                student_match["hostel"],

            "room":
                student_match["room"],

            "recognition_score":
                float(student_score)
        }


    # ========================================================
    # ADMITTED GUESTS
    # ========================================================

    guest_match, guest_score = (
        find_best_match(
            embedding,
            identity_cache.guests
        )
    )

    if guest_match is not None:

        return {

            "status": "ADMITTED_GUEST",

            "guest_id":
                guest_match["guest_id"],

            "expires_at":
                guest_match["expires_at"].isoformat(),

            "recognition_score":
                float(guest_score)
        }


    # ========================================================
    # UNKNOWN
    # ========================================================

    return {

        "status": "UNKNOWN",

        "message":
            "Face does not match any "
            "authorized identity",

        "recognition_score":
            float(
                max(
                    student_score,
                    guest_score
                )
            )
    }


# ============================================================
# RECOGNIZE ONE DETECTED FACE (IDENTITY + LIVENESS)
# ============================================================
#
# Single entry point for turning a detected face into a full
# recognition result. Every caller that matches a face against an
# identity — the single-image /recognize endpoint, the multi-camera
# pipeline, and the tracked live-camera service — should call this
# instead of recognize_embedding() directly, so the liveness check
# in §6.1/§13 of docs/PRD.md is enforced everywhere a face is
# matched, not just at one call site.

def recognize_face(frame, face):

    liveness = check_liveness(frame, face)

    result = recognize_embedding(
        face.embedding
    )

    result["is_live"] = liveness["is_live"]
    result["liveness_score"] = liveness["liveness_score"]

    if liveness["reasons"]:

        result["liveness_reasons"] = liveness["reasons"]

    return result


# ============================================================
# RECOGNIZE IMAGE
# ============================================================

def recognize_image(image):

    if image is None:

        return {
            "status": "NO_FACE",
            "message": "No image provided"
        }

    faces = app.get(image)

    if not faces:

        return {
            "status": "NO_FACE",
            "message": "No face detected"
        }

    face = faces[0]

    return recognize_face(
        image,
        face
    )