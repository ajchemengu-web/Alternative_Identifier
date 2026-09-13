import sqlite3
import uuid

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# SmartAccess case management (docs/PRD.md §8, Security Admin
# dashboard): a lightweight free-text case file — title/description,
# OPEN/CLOSED status, and an append-only note timeline
# (investigation_notes) — optionally tied to one watchlist target
# (watchlist_service.py). No formal link table to access_logs/
# unknown_persons entries; consistent with this codebase's existing
# no-foreign-key style (timetable's course/year, camera's
# department), evidence just gets referenced by id in a note's text.


def _row_to_dict(row):

    return dict(row) if row is not None else None


def create_case(title, description=None, target_id=None, opened_by=None):

    case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO investigations (
            case_id,
            title,
            description,
            target_id,
            status,
            opened_by
        )
        VALUES (?, ?, ?, ?, 'OPEN', ?)
    """, (
        case_id,
        title,
        description,
        target_id,
        opened_by
    ))

    connection.commit()

    connection.close()

    return get_case(case_id)


def list_cases(status=None):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    if status:

        cursor.execute("""
            SELECT * FROM investigations
            WHERE status = ?
            ORDER BY opened_at DESC
        """, (status.upper(),))

    else:

        cursor.execute(
            "SELECT * FROM investigations ORDER BY opened_at DESC"
        )

    rows = cursor.fetchall()

    connection.close()

    return [_row_to_dict(row) for row in rows]


def get_case(case_id):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM investigations WHERE case_id = ?",
        (case_id,)
    )

    case = _row_to_dict(cursor.fetchone())

    if case is None:

        connection.close()

        return None

    cursor.execute("""
        SELECT * FROM investigation_notes
        WHERE case_id = ?
        ORDER BY created_at ASC
    """, (case_id,))

    notes = [_row_to_dict(row) for row in cursor.fetchall()]

    connection.close()

    case["notes"] = notes

    return case


def add_note(case_id, note, author=None):

    if get_case(case_id) is None:

        raise ValueError(f"Unknown case_id: {case_id}")

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO investigation_notes (case_id, author, note)
        VALUES (?, ?, ?)
    """, (
        case_id,
        author,
        note
    ))

    connection.commit()

    connection.close()

    return get_case(case_id)


def close_case(case_id, closed_by):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE investigations
        SET status = 'CLOSED',
            closed_by = ?,
            closed_at = CURRENT_TIMESTAMP
        WHERE case_id = ?
    """, (
        closed_by,
        case_id
    ))

    connection.commit()

    updated = cursor.rowcount

    connection.close()

    return updated > 0


def reopen_case(case_id):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE investigations
        SET status = 'OPEN',
            closed_by = NULL,
            closed_at = NULL
        WHERE case_id = ?
    """, (
        case_id,
    ))

    connection.commit()

    updated = cursor.rowcount

    connection.close()

    return updated > 0
