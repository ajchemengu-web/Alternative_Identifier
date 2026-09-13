import os

import numpy as np

from src.db import get_connection
from src.services.recognition_service import (
    app,
    STUDENT_EMBEDDINGS_FOLDER
)


# ============================================================
# WHAT THIS IS
# ============================================================
#
# The live, HTTP-facing counterpart to src/enroll_students.py (which
# is an interactive webcam CLI script, not reachable from the API).
# Instead of capturing MAX_SAMPLES live webcam frames, this takes
# whatever reference photos the Enrollment Dashboard uploads for a
# student, computes one embedding per usable photo, and averages
# them — same "average several normalized samples" approach the CLI
# script uses, just fed by uploads instead of a live camera loop.
#
# Scope note: this only covers the STUDENT role, matching the
# existing `students` table (hostel/room are student-specific
# fields). Lecturer/Staff/Guard facial enrollment need their own
# table(s) before they can be wired up the same way — flagged here
# rather than forced into the student schema.
#
# department/course/year are optional, free-text (docs/PRD.md §8):
# they scope a student into the Dean of School Admin's roster and
# don't gate anything here — a student enrolled without them just
# doesn't show up in a department-filtered Dean view yet.


os.makedirs(
    STUDENT_EMBEDDINGS_FOLDER,
    exist_ok=True
)


def _safe_filename_component(value):

    return (
        value
        .replace("/", "-")
        .replace("\\", "-")
        .replace(" ", "_")
    )


def _embedding_from_image(image):

    faces = app.get(image)

    if len(faces) == 0:

        return None, "no_face_detected"

    if len(faces) > 1:

        return None, "multiple_faces_detected"

    embedding = faces[0].embedding

    return embedding / np.linalg.norm(embedding), None


def enroll_student_face(
    student_id,
    full_name,
    admission_number,
    hostel,
    room,
    images,
    department=None,
    course=None,
    year=None
):

    if not images:

        raise ValueError(
            "At least one reference photo is required."
        )

    samples = []
    skipped = []

    for image in images:

        embedding, reason = _embedding_from_image(image)

        if embedding is None:

            skipped.append(reason)

            continue

        samples.append(embedding)

    if not samples:

        raise ValueError(
            "None of the supplied photos had exactly one usable "
            f"face ({', '.join(skipped) if skipped else 'unknown reason'})."
        )

    final_embedding = np.mean(samples, axis=0)

    final_embedding = (
        final_embedding / np.linalg.norm(final_embedding)
    )

    embedding_filename = (
        f"{_safe_filename_component(student_id)}.npy"
    )

    embedding_path = os.path.join(
        STUDENT_EMBEDDINGS_FOLDER,
        embedding_filename
    )

    np.save(
        embedding_path,
        final_embedding
    )

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute("""
            INSERT INTO students (
                student_id,
                full_name,
                admission_number,
                hostel,
                room,
                department,
                course,
                year,
                embedding_file
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            student_id,
            full_name,
            admission_number,
            hostel,
            room,
            department,
            course,
            year,
            embedding_filename
        ))

        connection.commit()

    except Exception as error:

        # Roll back the embedding file so a failed enrollment doesn't
        # leave an orphaned template behind (same cleanup the
        # interactive CLI script does on a duplicate student_id).
        if os.path.exists(embedding_path):

            os.remove(embedding_path)

        connection.close()

        raise ValueError(
            "Could not enroll student — student_id or "
            f"admission_number may already exist ({error})"
        )

    connection.close()

    return {

        "student_id": student_id,

        "full_name": full_name,

        "admission_number": admission_number,

        "hostel": hostel,

        "room": room,

        "department": department,

        "course": course,

        "year": year,

        "samples_used": len(samples),

        "samples_skipped": len(skipped)
    }
