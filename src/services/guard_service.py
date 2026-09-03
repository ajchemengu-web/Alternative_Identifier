import os
import sqlite3
import shutil
from datetime import datetime, timedelta


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)
UNKNOWN_EMBEDDINGS_FOLDER = os.path.join(
    "data",
    "unknowns",
    "embeddings"
)


GUEST_EMBEDDINGS_FOLDER = os.path.join(
    "data",
    "guests",
    "embeddings"
)


os.makedirs(
    GUEST_EMBEDDINGS_FOLDER,
    exist_ok=True
)


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_connection():

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    return connection


# ==========================================
# GET PENDING UNKNOWN PERSONS
# ==========================================

def get_pending_unknowns():

    connection = get_connection()

    cursor = connection.cursor()


    cursor.execute("""
        SELECT
            unknown_id,
            image_path,
            status,
            detected_at
        FROM unknown_persons
        WHERE status = 'PENDING_REVIEW'
        ORDER BY detected_at DESC
    """)


    rows = cursor.fetchall()

    connection.close()


    unknowns = []


    for row in rows:

        unknowns.append({

            "unknown_id": row["unknown_id"],

            "image_path": row["image_path"],

            "status": row["status"],

            "detected_at": row["detected_at"]

        })


    return unknowns


# ==========================================
# REJECT UNKNOWN PERSON
# ==========================================

def reject_unknown_person(
    unknown_id,
    reviewed_by="Security Guard"
):

    connection = get_connection()

    cursor = connection.cursor()


    cursor.execute("""
        SELECT unknown_id
        FROM unknown_persons
        WHERE unknown_id = ?
    """, (
        unknown_id,
    ))


    person = cursor.fetchone()


    if person is None:

        connection.close()

        return {

            "success": False,

            "message": "Unknown person not found"
        }


    cursor.execute("""
        UPDATE unknown_persons

        SET
            status = ?,
            reviewed_at = ?,
            reviewed_by = ?

        WHERE unknown_id = ?
    """, (

        "REJECTED",

        datetime.now().isoformat(),

        reviewed_by,

        unknown_id

    ))


    connection.commit()

    connection.close()


    return {

        "success": True,

        "unknown_id": unknown_id,

        "status": "REJECTED",

        "message": "Access rejected"
    }


# ==========================================
# ADMIT UNKNOWN PERSON
# ==========================================

def admit_unknown_person(
    unknown_id,
    reviewed_by="Security Guard"
):

    connection = get_connection()

    cursor = connection.cursor()


    # --------------------------------------
    # FIND UNKNOWN PERSON
    # --------------------------------------

    cursor.execute("""
        SELECT
            unknown_id,
            image_path,
            embedding_file,
            status
        FROM unknown_persons
        WHERE unknown_id = ?
    """, (
        unknown_id,
    ))


    person = cursor.fetchone()


    if person is None:

        connection.close()

        return {

            "success": False,

            "message": "Unknown person not found"
        }


    # --------------------------------------
    # CHECK STATUS
    # --------------------------------------

    if person["status"] != "PENDING_REVIEW":

        connection.close()

        return {

            "success": False,

            "message": (
                f"This person has already been "
                f"reviewed: {person['status']}"
            )
        }

    # --------------------------------------
    # COPY FACE EMBEDDING TO GUEST STORAGE
    # --------------------------------------

    source_embedding = os.path.join(
        UNKNOWN_EMBEDDINGS_FOLDER,
        person["embedding_file"]
    )

    guest_id = (
        "AG-" +
        unknown_id.replace("UNK-", "")
    )

    guest_embedding_file = (
        f"{guest_id}.npy"
    )

    destination_embedding = os.path.join(
        GUEST_EMBEDDINGS_FOLDER,
        guest_embedding_file
    )

    if not os.path.exists(source_embedding):
        connection.close()
        return {
            "success": False,
            "message": "Unknown face embedding not found"
        }

    shutil.copy(
        source_embedding,
        destination_embedding
    )

    # --------------------------------------
    # SET 24 HOUR EXPIRATION
    # --------------------------------------

    expires_at = (
        datetime.now() +
        timedelta(hours=24)
    )

    # --------------------------------------
    # CREATE ADMITTED GUEST
    # --------------------------------------

    cursor.execute("""
        INSERT INTO guests (
            guest_id,
            embedding_file,
            status,
            expires_at
        )
        VALUES (?, ?, ?, ?)
    """, (
        guest_id,
        guest_embedding_file,
        "AG",
        expires_at.isoformat()
    ))

    # --------------------------------------
    # UPDATE UNKNOWN RECORD
    # --------------------------------------

    cursor.execute("""
        UPDATE unknown_persons
        SET
            status = ?,
            reviewed_at = ?,
            reviewed_by = ?
        WHERE unknown_id = ?
    """, (
        "ADMITTED",
        datetime.now().isoformat(),
        reviewed_by,
        unknown_id
    ))

    connection.commit()
    connection.close()

    result = {
        "success": True,
        "unknown_id": unknown_id,
        "guest_id": guest_id,
        "status": "AG",
        "expires_at": expires_at.isoformat(),
        "message": "Guest admitted successfully for 24 hours"
    }

    return result