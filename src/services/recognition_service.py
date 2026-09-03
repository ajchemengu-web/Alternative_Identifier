import os
import sqlite3
from datetime import datetime

import cv2
import numpy as np
from insightface.app import FaceAnalysis


# ==========================================
# PATHS
# ==========================================

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


# ==========================================
# LOAD AI MODEL
# ==========================================

print("Loading Face Recognition AI...")

app = FaceAnalysis(
    name="buffalo_l",
    providers=["CPUExecutionProvider"]
)

app.prepare(
    ctx_id=0,
    det_size=(640, 640)
)

print("✅ Face Recognition AI ready!")


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_connection():

    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row

    return connection


# ==========================================
# LOAD STUDENT IDENTITIES
# ==========================================

def load_students():

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

        if os.path.exists(embedding_path):

            embedding = np.load(embedding_path)

            embedding = embedding / np.linalg.norm(embedding)

            students.append({
                "student_id": student["student_id"],
                "full_name": student["full_name"],
                "admission_number": student["admission_number"],
                "hostel": student["hostel"],
                "room": student["room"],
                "embedding": embedding
            })

    return students


# ==========================================
# LOAD ACTIVE GUESTS
# ==========================================

def load_active_guests():

    guests = []

    connection = get_connection()
    cursor = connection.cursor()

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

        # Skip malformed expiry values
        if not guest["expires_at"]:
            continue

        try:
            expires_at = datetime.fromisoformat(
                guest["expires_at"]
            )
        except ValueError:
            continue


        # Skip expired guests
        if now >= expires_at:
            continue


        embedding_path = os.path.join(
            GUEST_EMBEDDINGS_FOLDER,
            guest["embedding_file"]
        )

        if os.path.exists(embedding_path):

            embedding = np.load(embedding_path)

            embedding = embedding / np.linalg.norm(embedding)

            guests.append({
                "guest_id": guest["guest_id"],
                "expires_at": expires_at,
                "embedding": embedding
            })

    return guests


# ==========================================
# FIND BEST MATCH
# ==========================================

def find_best_match(
    face_embedding,
    identities
):

    best_match = None
    best_score = -1


    for identity in identities:

        score = np.dot(
            face_embedding,
            identity["embedding"]
        )

        if score > best_score:

            best_score = score
            best_match = identity


    return best_match, best_score

def recognize_embedding(face_embedding):

    # Normalize embedding
    embedding = (
        face_embedding /
        np.linalg.norm(face_embedding)
    )


    # ======================================
    # CHECK STUDENTS
    # ======================================

    students = load_students()

    student_match, student_score = find_best_match(
        embedding,
        students
    )


    if (
        student_match is not None
        and student_score >= MATCH_THRESHOLD
    ):

        return {
            "status": "STUDENT",
            "student_id": student_match["student_id"],
            "full_name": student_match["full_name"],
            "admission_number": student_match[
                "admission_number"
            ],
            "hostel": student_match["hostel"],
            "room": student_match["room"],
            "recognition_score": float(student_score)
        }


    # ======================================
    # CHECK ACTIVE GUESTS
    # ======================================

    guests = load_active_guests()

    guest_match, guest_score = find_best_match(
        embedding,
        guests
    )


    if (
        guest_match is not None
        and guest_score >= MATCH_THRESHOLD
    ):

        return {
            "status": "ADMITTED_GUEST",
            "guest_id": guest_match["guest_id"],
            "expires_at": guest_match[
                "expires_at"
            ].isoformat(),
            "recognition_score": float(guest_score)
        }


    # ======================================
    # UNKNOWN
    # ======================================

    return {
        "status": "UNKNOWN",
        "message": (
            "Face does not match any "
            "authorized identity"
        )
    }


# ==========================================
# RECOGNIZE IMAGE
# ==========================================

def recognize_image(image):

    # Detect faces
    faces = app.get(image)


    if not faces:

        return {
            "status": "NO_FACE",
            "message": "No face detected"
        }


    # For now, process the first face
    face = faces[0]

    embedding = face.embedding

    embedding = (
        embedding /
        np.linalg.norm(embedding)
    )


    # ======================================
    # CHECK STUDENTS
    # ======================================

    students = load_students()

    student_match, student_score = find_best_match(
        embedding,
        students
    )


    if (
        student_match is not None
        and student_score >= MATCH_THRESHOLD
    ):

        return {
            "status": "STUDENT",
            "student_id": student_match["student_id"],
            "full_name": student_match["full_name"],
            "admission_number": student_match["admission_number"],
            "hostel": student_match["hostel"],
            "room": student_match["room"],
            "recognition_score": float(student_score)
        }


    # ======================================
    # CHECK ACTIVE GUESTS
    # ======================================

    guests = load_active_guests()

    guest_match, guest_score = find_best_match(
        embedding,
        guests
    )


    if (
        guest_match is not None
        and guest_score >= MATCH_THRESHOLD
    ):

        return {
            "status": "ADMITTED_GUEST",
            "guest_id": guest_match["guest_id"],
            "expires_at": guest_match["expires_at"].isoformat(),
            "recognition_score": float(guest_score)
        }


    # ======================================
    # UNKNOWN
    # ======================================

    return {
        "status": "UNKNOWN",
        "message": "Face does not match any authorized identity"
    }