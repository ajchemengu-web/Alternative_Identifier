import os
import sqlite3
import uuid

import numpy as np

from src.db import get_connection
from src.services.recognition_service import app


# ============================================================
# WHAT THIS IS
# ============================================================
#
# SmartAccess "target tracking" (docs/PRD.md §8, Security Admin
# dashboard): a target is a person of interest the Security/Original
# Admin registers, optionally with reference photos. A target with a
# stored embedding is checked by the live recognition pipeline
# (recognition_service.IdentityCache.targets, ahead of students/
# guests — a target flag overrides normal admission even for an
# otherwise-legitimate member) — see recognition_service.py and
# access_service.py for the match/logging path.
#
# "Tracking" a target concretely means: every live sighting gets its
# own access_logs row (person_type='TARGET', decision='TARGET_ALERT'),
# unlike STUDENT/GUEST which are cooldown-throttled — see
# get_sightings() below, which is that history.


TARGET_EMBEDDINGS_FOLDER = os.path.join(
    "data",
    "watchlist",
    "embeddings"
)

os.makedirs(
    TARGET_EMBEDDINGS_FOLDER,
    exist_ok=True
)

STATUSES = {
    "ACTIVE",
    "RESOLVED"
}


def _row_to_dict(row):

    return dict(row) if row is not None else None


def _embedding_from_image(image):

    faces = app.get(image)

    if len(faces) == 0:

        return None, "no_face_detected"

    if len(faces) > 1:

        return None, "multiple_faces_detected"

    embedding = faces[0].embedding

    return embedding / np.linalg.norm(embedding), None


def create_target(
    full_name,
    description=None,
    reason=None,
    images=None,
    created_by=None
):

    target_id = f"TGT-{uuid.uuid4().hex[:8].upper()}"

    embedding_filename = None

    if images:

        samples = []
        skipped = []

        for image in images:

            embedding, skip_reason = _embedding_from_image(image)

            if embedding is None:

                skipped.append(skip_reason)

                continue

            samples.append(embedding)

        if not samples:

            raise ValueError(
                "None of the supplied photos had exactly one usable "
                f"face ({', '.join(skipped) if skipped else 'unknown reason'})."
            )

        final_embedding = np.mean(samples, axis=0)

        final_embedding = final_embedding / np.linalg.norm(final_embedding)

        embedding_filename = f"{target_id}.npy"

        np.save(
            os.path.join(TARGET_EMBEDDINGS_FOLDER, embedding_filename),
            final_embedding
        )

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO watchlist_targets (
            target_id,
            full_name,
            description,
            reason,
            status,
            embedding_file,
            created_by
        )
        VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)
    """, (
        target_id,
        full_name,
        description,
        reason,
        embedding_filename,
        created_by
    ))

    connection.commit()

    connection.close()

    return get_target(target_id)


def get_target(target_id):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM watchlist_targets WHERE target_id = ?",
        (target_id,)
    )

    row = cursor.fetchone()

    connection.close()

    return _row_to_dict(row)


def list_targets(status=None):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    if status:

        cursor.execute("""
            SELECT * FROM watchlist_targets
            WHERE status = ?
            ORDER BY created_at DESC
        """, (status.upper(),))

    else:

        cursor.execute(
            "SELECT * FROM watchlist_targets ORDER BY created_at DESC"
        )

    rows = cursor.fetchall()

    connection.close()

    return [_row_to_dict(row) for row in rows]


def resolve_target(target_id, resolved_by):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE watchlist_targets
        SET status = 'RESOLVED',
            resolved_by = ?,
            resolved_at = CURRENT_TIMESTAMP
        WHERE target_id = ?
    """, (
        resolved_by,
        target_id
    ))

    connection.commit()

    updated = cursor.rowcount

    connection.close()

    return updated > 0


def reactivate_target(target_id):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE watchlist_targets
        SET status = 'ACTIVE',
            resolved_by = NULL,
            resolved_at = NULL
        WHERE target_id = ?
    """, (
        target_id,
    ))

    connection.commit()

    updated = cursor.rowcount

    connection.close()

    return updated > 0


def get_sightings(target_id):

    # The actual "tracking" view: every access_logs row this target
    # has produced, in one place, newest first — see this module's
    # docstring for why target matches skip the cooldown that
    # otherwise throttles repeated STUDENT/GUEST logging.

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT * FROM access_logs
        WHERE person_type = 'TARGET' AND person_identifier = ?
        ORDER BY timestamp DESC
    """, (target_id,))

    rows = cursor.fetchall()

    connection.close()

    return [_row_to_dict(row) for row in rows]
