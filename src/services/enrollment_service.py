import os
import sqlite3

import numpy as np

from src.db import get_connection
from src.services.recognition_service import (
    app,
    STUDENT_EMBEDDINGS_FOLDER
)
from src.services.liveness_service import check_liveness


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
# department/course/year/semester are optional, free-text
# (docs/PRD.md §8): department/course/year scope a student into the
# Dean of School Admin's roster, and semester (with course/year) is
# what SmartAttendance matches against a timetable_entries.semester
# to route the right half-year's schedule to the student — none of
# them gate anything here, a student enrolled without them just
# doesn't show up in a department-filtered Dean view or get a
# semester-scoped schedule match yet.


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


# Same single-face check as _embedding_from_image above, plus the
# passive liveness heuristic (liveness_service.py) — used only for
# self-enrollment (enroll_own_face below), where there's no admin in
# the loop to catch someone submitting a photo of a photo. Admin-run
# enrollment (enroll_student_face) doesn't need this: an admin is
# physically present taking the reference photos.
def _live_embedding_from_image(image):

    faces = app.get(image)

    if len(faces) == 0:

        return None, "no_face_detected", None

    if len(faces) > 1:

        return None, "multiple_faces_detected", None

    face = faces[0]

    liveness = check_liveness(image, face)

    if not liveness["is_live"]:

        reason = "liveness_check_failed"

        if liveness["reasons"]:

            reason += ":" + ",".join(liveness["reasons"])

        return None, reason, liveness["liveness_score"]

    embedding = face.embedding

    return (
        embedding / np.linalg.norm(embedding),
        None,
        liveness["liveness_score"]
    )


# ============================================================
# REGISTER A STUDENT RECORD (no embedding yet)
# ============================================================
#
# An admin creates the record (docs/PRD.md §5) — the same details
# enroll_student_face below used to require alongside a photo — but
# leaves embedding_file NULL. A student then self-enrolls their own
# face onto this same record via enroll_own_face, from their own
# logged-in session, instead of an admin capturing/uploading photos
# on their behalf.

def create_student_record(
    student_id,
    full_name,
    admission_number,
    hostel,
    room,
    department=None,
    course=None,
    year=None,
    semester=None
):

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
                semester,
                embedding_file
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """, (
            student_id,
            full_name,
            admission_number,
            hostel,
            room,
            department,
            course,
            year,
            semester
        ))

        connection.commit()

    except Exception as error:

        connection.close()

        raise ValueError(
            "Could not register student — student_id or "
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

        "semester": semester,

        "face_enrolled": False
    }


def enroll_student_face(
    student_id,
    full_name,
    admission_number,
    hostel,
    room,
    images,
    department=None,
    course=None,
    year=None,
    semester=None
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
                semester,
                embedding_file
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            student_id,
            full_name,
            admission_number,
            hostel,
            room,
            department,
            course,
            year,
            semester,
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

        "semester": semester,

        "samples_used": len(samples),

        "samples_skipped": len(skipped)
    }


# ============================================================
# SELF-ENROLL MY OWN FACE (STUDENT, logged in)
# ============================================================
#
# Counterpart to enroll_student_face above, but for a STUDENT
# enrolling themselves (docs/PRD.md §5) rather than an admin
# enrolling them: resolves the caller's own student record via
# users.linked_person_id (same lookup me_service.py's "my profile"
# uses), requires that record to already exist (created by an admin
# via create_student_record — no self-registration, docs/PRD.md §9),
# and UPDATEs its embedding_file instead of INSERTing a new row.
# Every candidate photo also has to pass the liveness check
# (liveness_service.py) — an admin enrollment doesn't need that
# check because an admin is physically present taking the photos;
# self-enrollment has no one else in the loop to catch a spoofed
# photo.

def enroll_own_face(username, images):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT linked_person_id
        FROM users
        WHERE username = ?
    """, (
        username,
    ))

    user_row = cursor.fetchone()

    if user_row is None or user_row["linked_person_id"] is None:

        connection.close()

        raise ValueError(
            "No linked student profile found for this account."
        )

    student_id = user_row["linked_person_id"]

    cursor.execute("""
        SELECT student_id, full_name
        FROM students
        WHERE student_id = ?
    """, (
        student_id,
    ))

    student_row = cursor.fetchone()

    if student_row is None:

        connection.close()

        raise ValueError(
            "Your student record hasn't been set up yet — contact "
            "an admin."
        )

    if not images:

        connection.close()

        raise ValueError(
            "At least one photo is required."
        )

    samples = []
    skipped = []
    liveness_scores = []

    for image in images:

        embedding, reason, liveness_score = _live_embedding_from_image(
            image
        )

        if embedding is None:

            skipped.append(reason)

            continue

        samples.append(embedding)

        liveness_scores.append(liveness_score)

    if not samples:

        connection.close()

        raise ValueError(
            "None of the supplied photos passed the liveness check "
            f"({', '.join(skipped) if skipped else 'unknown reason'}). "
            "Try again somewhere well-lit, facing the camera "
            "directly, without a screen or printed photo in view."
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

    cursor.execute("""
        UPDATE students
        SET embedding_file = ?
        WHERE student_id = ?
    """, (
        embedding_filename,
        student_id
    ))

    connection.commit()

    connection.close()

    return {

        "student_id": student_id,

        "full_name": student_row["full_name"],

        "samples_used": len(samples),

        "samples_skipped": len(skipped),

        "average_liveness_score": (
            sum(liveness_scores) / len(liveness_scores)
            if liveness_scores else None
        )
    }
