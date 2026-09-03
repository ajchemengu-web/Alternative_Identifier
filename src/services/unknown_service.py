import os
import sqlite3
import uuid
from datetime import datetime

import cv2
import numpy as np

from src.services.recognition_service import app


# ==========================================
# PATHS
# ==========================================

DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)

UNKNOWN_IMAGES_FOLDER = os.path.join(
    "data",
    "unknowns"
)

UNKNOWN_EMBEDDINGS_FOLDER = os.path.join(
    "data",
    "unknowns",
    "embeddings"
)


os.makedirs(
    UNKNOWN_IMAGES_FOLDER,
    exist_ok=True
)

os.makedirs(
    UNKNOWN_EMBEDDINGS_FOLDER,
    exist_ok=True
)


# ==========================================
# CONFIGURATION
# ==========================================

UNKNOWN_MATCH_THRESHOLD = 0.55


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_connection():

    return sqlite3.connect(DATABASE_PATH)


# ==========================================
# NORMALIZE EMBEDDING
# ==========================================

def normalize_embedding(embedding):

    norm = np.linalg.norm(embedding)

    if norm == 0:
        return embedding

    return embedding / norm


# ==========================================
# LOAD EXISTING UNKNOWN EMBEDDINGS
# ==========================================

def load_unknown_embeddings():

    unknowns = []

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            unknown_id,
            embedding_file,
            status,
            detected_at
        FROM unknown_persons
        WHERE embedding_file IS NOT NULL
        AND status = 'PENDING_REVIEW'
    """)

    rows = cursor.fetchall()

    connection.close()


    for row in rows:

        unknown_id = row[0]
        embedding_file = row[1]

        embedding_path = os.path.join(
            UNKNOWN_EMBEDDINGS_FOLDER,
            embedding_file
        )


        if os.path.exists(embedding_path):

            embedding = np.load(embedding_path)

            embedding = normalize_embedding(
                embedding
            )

            unknowns.append({

                "unknown_id": unknown_id,

                "embedding": embedding

            })


    return unknowns


# ==========================================
# FIND DUPLICATE UNKNOWN
# ==========================================

def find_duplicate_unknown(
    face_embedding,
    unknowns
):

    best_match = None
    best_score = -1


    for unknown in unknowns:

        score = np.dot(

            face_embedding,

            unknown["embedding"]

        )


        if score > best_score:

            best_score = score
            best_match = unknown


    if (
        best_match is not None
        and best_score >= UNKNOWN_MATCH_THRESHOLD
    ):

        return best_match, best_score


    return None, best_score


# ==========================================
# CREATE OR FIND UNKNOWN PERSON
# ==========================================

def create_unknown_person(image):

    # --------------------------------------
    # DETECT FACE
    # --------------------------------------

    faces = app.get(image)


    if not faces:

        raise Exception(
            "No face detected in unknown person image."
        )


    # Use the first detected face
    face = faces[0]

    face_embedding = normalize_embedding(
        face.embedding
    )


    # --------------------------------------
    # CHECK FOR DUPLICATES
    # --------------------------------------

    existing_unknowns = load_unknown_embeddings()

    duplicate, duplicate_score = (
        find_duplicate_unknown(

            face_embedding,

            existing_unknowns

        )
    )


    # --------------------------------------
    # SAME UNKNOWN PERSON FOUND
    # --------------------------------------

    if duplicate is not None:

        return {

            "unknown_id": duplicate[
                "unknown_id"
            ],

            "status": "PENDING_REVIEW",

            "duplicate": True,

            "recognition_score": float(
                duplicate_score
            )

        }


    # --------------------------------------
    # NEW UNKNOWN PERSON
    # --------------------------------------

    unique_code = uuid.uuid4().hex[:8].upper()

    unknown_id = f"UNK-{unique_code}"


    # --------------------------------------
    # SAVE IMAGE
    # --------------------------------------

    image_filename = f"{unknown_id}.jpg"

    image_path = os.path.join(
        UNKNOWN_IMAGES_FOLDER,
        image_filename
    )


    saved = cv2.imwrite(
        image_path,
        image
    )


    if not saved:

        raise Exception(
            "Could not save unknown person image."
        )


    # --------------------------------------
    # SAVE EMBEDDING
    # --------------------------------------

    embedding_filename = f"{unknown_id}.npy"

    embedding_path = os.path.join(
        UNKNOWN_EMBEDDINGS_FOLDER,
        embedding_filename
    )


    np.save(
        embedding_path,
        face_embedding
    )


    # --------------------------------------
    # SAVE DATABASE RECORD
    # --------------------------------------

    connection = get_connection()
    cursor = connection.cursor()


    cursor.execute("""
        INSERT INTO unknown_persons (

            unknown_id,
            image_path,
            embedding_file,
            status

        )

        VALUES (?, ?, ?, ?)
    """, (

        unknown_id,
        image_path,
        embedding_filename,
        "PENDING_REVIEW"

    ))


    connection.commit()
    connection.close()


    # --------------------------------------
    # RETURN RESULT
    # --------------------------------------

    return {

        "unknown_id": unknown_id,

        "status": "PENDING_REVIEW",

        "duplicate": False,

        "image_path": image_path,

        "detected_at": datetime.now().isoformat()

    }