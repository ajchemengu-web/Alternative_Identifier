import os
import sqlite3
from datetime import datetime, timedelta

import numpy as np

from src.db import get_connection as _get_raw_connection
from src.services.liveness_service import check_liveness
from src.services import template_store
from src.services.recognition_service import (
    app,
    find_best_match,
    STUDENT_EMBEDDINGS_FOLDER,
)


# ============================================================
# WHAT THIS IS
# ============================================================
#
# The classroom-camera attendance pipeline (docs/PRD.md §7.1):
#
#   1. A session activates 20 minutes before the lesson's start time.
#   2. Recognized attendees are timestamped as seen.
#   3. The session deactivates 35 minutes in — no new "present" marks
#      after this.
#   4. The roll is submitted at the 40-minute mark: everyone not yet
#      seen is marked absent, and every expected student gets a
#      notification.
#   5. Anyone first recognized after the 35-minute cutoff is marked
#      absent for that session, even if seen later — enforced here by
#      get_active_session_for_camera() simply refusing to hand back a
#      session once "now" is past its cutoff_at, so record_attendance()
#      is never even called for a too-late frame.
#
# Deliberately does NOT reuse recognize_image()/recognize_face(): those
# always check watchlist targets and guests ahead of students (see
# recognition_service.py's own docstring), which don't belong in a
# classroom-attendance decision. Liveness is still enforced directly
# via check_liveness(), same as everywhere else a face is matched —
# without it, a printed photo held up to the camera could mark someone
# present who isn't there.
#
# "Expected students" for a session = the same loose course/department
# /year/semester match already used everywhere else in this codebase
# (timetable_service.list_entries, the Flutter app's own timetable
# fetch) — there is no separate enrollment/roster table in this schema.


ACTIVATE_BEFORE_MINUTES = 20
CUTOFF_AFTER_MINUTES = 35
SUBMIT_AFTER_MINUTES = 40

_WEEKDAY_NAMES = [
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
]


def get_connection():

    connection = _get_raw_connection()

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# TIME WINDOW HELPERS
# ============================================================

def _parse_time_on_date(date_obj, time_str):

    hour, minute = (int(part) for part in time_str.split(":")[:2])

    return datetime.combine(date_obj, datetime.min.time()).replace(
        hour=hour,
        minute=minute
    )


def _session_window(entry, session_date):

    start = _parse_time_on_date(session_date, entry["start_time"])

    return {
        "activates_at": start - timedelta(minutes=ACTIVATE_BEFORE_MINUTES),
        "cutoff_at": start + timedelta(minutes=CUTOFF_AFTER_MINUTES),
        "submit_at": start + timedelta(minutes=SUBMIT_AFTER_MINUTES),
    }


# ============================================================
# ROSTER LOADING (mirrors recognition_service.IdentityCache's
# load_students(), scoped to one timetable entry's expected students
# instead of the whole population)
# ============================================================

def _load_roster_identities(cursor, entry):

    query = (
        "SELECT student_id, full_name, embedding_file FROM students "
        "WHERE course = ? AND year = ?"
    )

    params = [entry["course"], entry["year"]]

    if entry["department"]:

        query += " AND department = ?"

        params.append(entry["department"])

    if entry["semester"] is not None:

        query += " AND semester = ?"

        params.append(entry["semester"])

    cursor.execute(query, params)

    identities = []

    for row in cursor.fetchall():

        if not row["embedding_file"]:

            continue

        embedding_path = os.path.join(
            STUDENT_EMBEDDINGS_FOLDER,
            row["embedding_file"]
        )

        if not os.path.exists(embedding_path):

            continue

        embedding = template_store.load_template(
            embedding_path
        ).astype(np.float32)

        norm = np.linalg.norm(embedding)

        if norm == 0:

            continue

        identities.append({
            "student_id": row["student_id"],
            "full_name": row["full_name"],
            "embedding": embedding / norm,
        })

    return identities


# ============================================================
# SESSION LOOKUP / LAZY CREATION
# ============================================================

def _get_or_open_session(cursor, entry, session_date, now):

    cursor.execute(
        "SELECT * FROM class_sessions "
        "WHERE timetable_entry_id = ? AND session_date = ?",
        (entry["id"], session_date)
    )

    existing = cursor.fetchone()

    if existing is not None:

        return existing

    window = _session_window(entry, now.date())

    if now < window["activates_at"]:

        return None

    cursor.execute(
        "INSERT INTO class_sessions "
        "(timetable_entry_id, session_date, status, "
        "activates_at, cutoff_at, submit_at) "
        "VALUES (?, ?, 'ACTIVE', ?, ?, ?)",
        (
            entry["id"],
            session_date,
            window["activates_at"].isoformat(),
            window["cutoff_at"].isoformat(),
            window["submit_at"].isoformat(),
        )
    )

    cursor.execute(
        "SELECT * FROM class_sessions "
        "WHERE timetable_entry_id = ? AND session_date = ?",
        (entry["id"], session_date)
    )

    return cursor.fetchone()


def get_active_session_for_camera(camera_id, now=None):

    from src.services import camera_service

    now = now or datetime.now()

    camera = camera_service.get_camera(camera_id)

    if (
        camera is None
        or camera.get("camera_type") != "CLASSROOM"
        or not camera.get("location")
    ):

        return None

    weekday_name = _WEEKDAY_NAMES[now.weekday()]

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM timetable_entries "
        "WHERE status = 'ON' AND UPPER(day_of_week) = ? "
        "AND LOWER(venue) = LOWER(?)",
        (weekday_name, camera["location"])
    )

    entries = cursor.fetchall()

    today = now.date().isoformat()

    for entry in entries:

        session = _get_or_open_session(cursor, entry, today, now)

        if session is None:

            continue

        cutoff_at = datetime.fromisoformat(session["cutoff_at"])

        if now < cutoff_at:

            connection.commit()
            connection.close()

            return session

    connection.commit()
    connection.close()

    return None


# ============================================================
# RECORDING A RECOGNIZED FACE
# ============================================================

def record_attendance(class_session_id, image):

    if image is None:

        return {"status": "NO_FACE", "message": "No image provided"}

    faces = app.get(image)

    if not faces:

        return {"status": "NO_FACE", "message": "No face detected"}

    face = faces[0]

    liveness = check_liveness(image, face)

    if not liveness["is_live"]:

        return {
            "status": "LIVENESS_FAILED",
            "liveness_score": liveness["liveness_score"],
            "reasons": liveness["reasons"],
        }

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM class_sessions WHERE id = ?",
        (class_session_id,)
    )

    session = cursor.fetchone()

    if session is None:

        connection.close()

        return {"status": "NO_SESSION"}

    cursor.execute(
        "SELECT * FROM timetable_entries WHERE id = ?",
        (session["timetable_entry_id"],)
    )

    entry = cursor.fetchone()

    identities = _load_roster_identities(cursor, entry)

    match, score = find_best_match(face.embedding, identities)

    if match is None:

        connection.close()

        return {"status": "UNKNOWN", "recognition_score": score}

    cursor.execute(
        "SELECT id FROM attendance_records "
        "WHERE class_session_id = ? AND student_id = ?",
        (class_session_id, match["student_id"])
    )

    already_recorded = cursor.fetchone() is not None

    if not already_recorded:

        cursor.execute(
            "INSERT INTO attendance_records "
            "(class_session_id, student_id, status, "
            "recognized_at, recognition_score) "
            "VALUES (?, ?, 'PRESENT', ?, ?)",
            (
                class_session_id,
                match["student_id"],
                datetime.now().isoformat(),
                score
            )
        )

        connection.commit()

    connection.close()

    return {
        "status": "STUDENT",
        "student_id": match["student_id"],
        "full_name": match["full_name"],
        "recognition_score": score,
        "already_recorded": already_recorded,
    }


# ============================================================
# SWEEP (mirrors the retention sweep's lifespan-loop pattern in
# src/api/main.py: opens due sessions, finalizes ones past their
# submit_at mark)
# ============================================================

def _submit_session(cursor, session):

    cursor.execute(
        "SELECT * FROM timetable_entries WHERE id = ?",
        (session["timetable_entry_id"],)
    )

    entry = cursor.fetchone()

    if entry is not None:

        roster = _load_roster_identities(cursor, entry)

        cursor.execute(
            "SELECT student_id FROM attendance_records "
            "WHERE class_session_id = ?",
            (session["id"],)
        )

        already_seen = {
            row["student_id"] for row in cursor.fetchall()
        }

        for identity in roster:

            if identity["student_id"] in already_seen:

                continue

            cursor.execute(
                "INSERT INTO attendance_records "
                "(class_session_id, student_id, status) "
                "VALUES (?, ?, 'ABSENT')",
                (session["id"], identity["student_id"])
            )

        cursor.execute(
            "SELECT student_id, status FROM attendance_records "
            "WHERE class_session_id = ?",
            (session["id"],)
        )

        for row in cursor.fetchall():

            kind = "ATTENDED" if row["status"] == "PRESENT" else "MISSED"

            cursor.execute(
                "INSERT INTO attendance_notifications "
                "(student_id, class_session_id, kind, "
                "unit_name, facilitator) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    row["student_id"],
                    session["id"],
                    kind,
                    entry["unit_name"],
                    entry["facilitator"]
                )
            )

    cursor.execute(
        "UPDATE class_sessions "
        "SET status = 'SUBMITTED', submitted_at = ? "
        "WHERE id = ?",
        (datetime.now().isoformat(), session["id"])
    )


def run_sweep(now=None):

    now = now or datetime.now()

    weekday_name = _WEEKDAY_NAMES[now.weekday()]
    today = now.date().isoformat()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM timetable_entries "
        "WHERE status = 'ON' AND UPPER(day_of_week) = ?",
        (weekday_name,)
    )

    entries = cursor.fetchall()

    opened_session_ids = []

    for entry in entries:

        session = _get_or_open_session(cursor, entry, today, now)

        if session is not None:

            opened_session_ids.append(session["id"])

    connection.commit()

    cursor.execute(
        "SELECT * FROM class_sessions "
        "WHERE status = 'ACTIVE' AND submit_at <= ?",
        (now.isoformat(),)
    )

    due_sessions = cursor.fetchall()

    submitted_session_ids = []

    for session in due_sessions:

        _submit_session(cursor, session)

        submitted_session_ids.append(session["id"])

    connection.commit()
    connection.close()

    return {
        "opened_session_ids": opened_session_ids,
        "submitted_session_ids": submitted_session_ids,
    }
