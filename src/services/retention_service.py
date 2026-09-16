import os
import sqlite3
from datetime import datetime

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# Enforces docs/PRD.md §9's retention/deletion rules, which are
# called out there as hard requirements, not optional hardening:
#
#   - Rejected guest facial data -> deleted immediately.
#   - Admitted guest facial data -> deleted automatically 24 hours
#     after admission.
#   - Student data -> deleted after graduation, via an explicit
#     admin action (not covered here — that's a manual admin flow
#     by design, see docs/PRD.md §9.4's decision note).
#
# Neither of the first two was actually wired up before this: a
# rejected unknown_persons row kept its image/embedding files on
# disk indefinitely, and an admitted guest's 24-hour `expires_at`
# was only ever used to deny recognition after the fact (see
# recognition_service.py) — nothing purged the files themselves.


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


def _safe_remove(path):

    if not path:

        return False

    if not os.path.exists(path):

        return False

    os.remove(path)

    return True


# ============================================================
# REJECTED GUEST -> IMMEDIATE DELETION
# ============================================================

def purge_rejected_person(unknown_id):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT image_path, embedding_file
        FROM unknown_persons
        WHERE unknown_id = ?
    """, (
        unknown_id,
    ))

    row = cursor.fetchone()

    connection.close()

    if row is None:

        return False

    _safe_remove(row["image_path"])

    if row["embedding_file"]:

        _safe_remove(os.path.join(
            UNKNOWN_EMBEDDINGS_FOLDER,
            row["embedding_file"]
        ))

    return True


# ============================================================
# ADMITTED GUEST -> AUTOMATIC 24-HOUR DELETION
# ============================================================

def purge_expired_guests(now=None):

    now = now or datetime.now()

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT guest_id, photo_path, embedding_file, expires_at
        FROM guests
        WHERE status = 'AG'
    """)

    rows = cursor.fetchall()

    purged_guest_ids = []

    for row in rows:

        if not row["expires_at"]:

            continue

        expires_at = datetime.fromisoformat(row["expires_at"])

        if now < expires_at:

            continue

        _safe_remove(row["photo_path"])

        if row["embedding_file"]:

            _safe_remove(os.path.join(
                GUEST_EMBEDDINGS_FOLDER,
                row["embedding_file"]
            ))

        cursor.execute("""
            UPDATE guests
            SET status = 'EXPIRED', photo_path = NULL, embedding_file = NULL
            WHERE guest_id = ?
        """, (
            row["guest_id"],
        ))

        purged_guest_ids.append(row["guest_id"])

    connection.commit()

    connection.close()

    return purged_guest_ids
