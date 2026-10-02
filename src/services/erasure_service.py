import json
import os
import sqlite3
import uuid

from src.db import get_connection as _get_raw_connection
from src.services.recognition_service import (
    identity_cache,
    STUDENT_EMBEDDINGS_FOLDER
)


# ============================================================
# WHAT THIS IS
# ============================================================
#
# Erases one student's personal data (docs/PRD.md §9.4: "student data
# → deleted after graduation", triggered by an explicit admin action;
# also how a data subject's erasure request is carried out). It is
# deliberately a separate, heavy, irreversible action — withdrawing
# consent (enrollment_service.withdraw_own_face_data) only removes the
# face template and leaves the student's record, login and history.
#
# What is erased, in one database transaction:
#   - the student record and their login account (role STUDENT)
#   - their access-log entries (person_type STUDENT)
#   - their class attendance records and attendance notifications
#   - their biometric consent history
# and, after that commits, their stored face template file.
#
# What is deliberately NOT touched, and is reported back instead:
#   - A SecurityAdmin's watchlist target created from this student. If
#     it is ACTIVE the erasure is refused (ErasureBlockedError): erasing
#     a person out from under a live security case is a human decision,
#     not something an endpoint should do silently. If it is RESOLVED,
#     the copied face template and the link back to this student are
#     removed, but the target record itself (its name, reason and
#     sighting history) is kept for the Security Admin to review — it
#     is reported in `retained_for_review`.
#   - Git history, backups, and any copy outside this application. This
#     service cannot reach those; see docs/DPIA.md.
#
# The erasure log stores NO identifier of the student, and the reason
# is a fixed choice rather than free text, so the log can prove an
# erasure happened without itself retaining who it was about. The
# erasure_reference returned is how the requester is later shown that.

REASONS = {
    "GRADUATED",
    "LEFT_INSTITUTION",
    "SUBJECT_REQUEST",
    "OTHER",
}


class ErasureBlockedError(Exception):

    def __init__(self, message, active_watchlist_targets):

        super().__init__(message)

        self.active_watchlist_targets = active_watchlist_targets


class NothingToEraseError(Exception):

    pass


def get_connection():

    connection = _get_raw_connection()

    connection.row_factory = sqlite3.Row

    return connection


def _count(cursor, query, params):

    cursor.execute(query, params)

    return cursor.fetchone()["n"]


def _gather(cursor, student_id):

    cursor.execute(
        "SELECT embedding_file FROM students WHERE student_id = ?",
        (student_id,)
    )

    student = cursor.fetchone()

    cursor.execute(
        "SELECT target_id, status, embedding_file FROM watchlist_targets "
        "WHERE linked_student_id = ?",
        (student_id,)
    )

    targets = [dict(row) for row in cursor.fetchall()]

    return {

        "student_record": student is not None,

        "embedding_file": student["embedding_file"] if student else None,

        "login_accounts": _count(
            cursor,
            "SELECT COUNT(*) AS n FROM users "
            "WHERE role = 'STUDENT' AND linked_person_id = ?",
            (student_id,)
        ),

        "access_log_entries": _count(
            cursor,
            "SELECT COUNT(*) AS n FROM access_logs "
            "WHERE person_type = 'STUDENT' AND person_identifier = ?",
            (student_id,)
        ),

        "attendance_records": _count(
            cursor,
            "SELECT COUNT(*) AS n FROM attendance_records "
            "WHERE student_id = ?",
            (student_id,)
        ),

        "attendance_notifications": _count(
            cursor,
            "SELECT COUNT(*) AS n FROM attendance_notifications "
            "WHERE student_id = ?",
            (student_id,)
        ),

        "consent_records": _count(
            cursor,
            "SELECT COUNT(*) AS n FROM biometric_consents "
            "WHERE student_id = ?",
            (student_id,)
        ),

        "watchlist_targets": targets,
    }


def _public_summary(found):

    return {

        "student_record": found["student_record"],

        "face_template": bool(found["embedding_file"]),

        "login_accounts": found["login_accounts"],

        "access_log_entries": found["access_log_entries"],

        "attendance_records": found["attendance_records"],

        "attendance_notifications": found["attendance_notifications"],

        "consent_records": found["consent_records"],

        "active_watchlist_targets": [
            t["target_id"] for t in found["watchlist_targets"]
            if t["status"] == "ACTIVE"
        ],

        "resolved_watchlist_targets": [
            t["target_id"] for t in found["watchlist_targets"]
            if t["status"] != "ACTIVE"
        ],
    }


def _has_any_data(found):

    return (
        found["student_record"]
        or found["login_accounts"]
        or found["access_log_entries"]
        or found["attendance_records"]
        or found["attendance_notifications"]
        or found["consent_records"]
        or found["watchlist_targets"]
    )


# ============================================================
# DRY RUN: WHAT WOULD BE ERASED
# ============================================================
#
# Counts only — no content. Lets an admin check what an erasure will
# touch (and whether it will be blocked) before doing it, and doubles
# as a quick "what do we hold on this person" answer.

def summarize_student_data(student_id):

    connection = get_connection()

    found = _gather(connection.cursor(), student_id)

    connection.close()

    if not _has_any_data(found):

        raise NothingToEraseError(
            "No data is held for that student_id."
        )

    return _public_summary(found)


def _remove_file(folder, filename):

    if not filename:

        return False

    # The filename comes from a database column. It is always a bare
    # name the application generated, but this deletes files, so refuse
    # anything that could point outside the folder rather than trust it.
    if os.path.basename(filename) != filename or filename in (".", ".."):

        raise OSError(f"refusing to delete unsafe filename: {filename!r}")

    path = os.path.join(folder, filename)

    if os.path.exists(path):

        os.remove(path)

        return True

    return False


# ============================================================
# ERASE
# ============================================================

def erase_student(student_id, confirm, reason, erased_by):

    if confirm != student_id:

        raise ValueError(
            "confirm must exactly match the student_id being erased."
        )

    if reason not in REASONS:

        raise ValueError(
            f"reason must be one of: {', '.join(sorted(REASONS))}."
        )

    connection = get_connection()

    cursor = connection.cursor()

    found = _gather(cursor, student_id)

    if not _has_any_data(found):

        connection.close()

        raise NothingToEraseError(
            "No data is held for that student_id."
        )

    active = [
        t["target_id"] for t in found["watchlist_targets"]
        if t["status"] == "ACTIVE"
    ]

    if active:

        connection.close()

        raise ErasureBlockedError(
            "This student is linked to an active watchlist target. "
            "Have the Security Admin resolve it first.",
            active
        )

    summary = _public_summary(found)

    reference = str(uuid.uuid4())

    try:

        cursor.execute(
            "DELETE FROM attendance_notifications WHERE student_id = ?",
            (student_id,)
        )

        cursor.execute(
            "DELETE FROM attendance_records WHERE student_id = ?",
            (student_id,)
        )

        cursor.execute(
            "DELETE FROM access_logs "
            "WHERE person_type = 'STUDENT' AND person_identifier = ?",
            (student_id,)
        )

        cursor.execute(
            "DELETE FROM biometric_consents WHERE student_id = ?",
            (student_id,)
        )

        cursor.execute(
            "DELETE FROM users "
            "WHERE role = 'STUDENT' AND linked_person_id = ?",
            (student_id,)
        )

        cursor.execute(
            "UPDATE watchlist_targets "
            "SET embedding_file = NULL, linked_student_id = NULL "
            "WHERE linked_student_id = ?",
            (student_id,)
        )

        cursor.execute(
            "DELETE FROM students WHERE student_id = ?",
            (student_id,)
        )

        cursor.execute(
            "INSERT INTO data_erasure_log "
            "(erasure_reference, reason, erased_by, summary) "
            "VALUES (?, ?, ?, ?)",
            (reference, reason, erased_by, json.dumps(summary))
        )

        connection.commit()

    except Exception:

        connection.rollback()

        connection.close()

        raise

    connection.close()

    # Files can't be rolled back, so they go only after the database
    # commit succeeded: a failure above leaves everything intact; a
    # failure here leaves an orphan file, which is reported rather than
    # hidden.
    files_removed = []
    files_failed = []

    from src.services.watchlist_service import TARGET_EMBEDDINGS_FOLDER

    to_remove = [(STUDENT_EMBEDDINGS_FOLDER, found["embedding_file"])] + [
        (TARGET_EMBEDDINGS_FOLDER, t["embedding_file"])
        for t in found["watchlist_targets"]
    ]

    for folder, filename in to_remove:

        if not filename:

            continue

        try:

            if _remove_file(folder, filename):

                files_removed.append(filename)

        except OSError:

            files_failed.append(filename)

    identity_cache.refresh()

    return {

        "erasure_reference": reference,

        "reason": reason,

        "erased": summary,

        "face_files_removed": len(files_removed),

        "face_files_failed": files_failed,

        "retained_for_review": {
            "watchlist_target_records": summary["resolved_watchlist_targets"],
        },

        "not_covered": [
            "Copies in git history, backups, or exports outside this "
            "application."
        ],
    }
