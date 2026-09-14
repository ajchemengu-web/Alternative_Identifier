import sqlite3
import uuid

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# SmartAccess case management (docs/PRD.md §8, Security Admin
# dashboard): a lightweight free-text case file — title/description,
# OPEN/CLOSED status, severity, an assignee, and an append-only note
# timeline (investigation_notes) — with a "primary" watchlist target
# (target_id) plus two link tables for everything else a case can
# reference: investigation_targets (additional targets) and
# investigation_unknowns (unknown_persons sightings a case is built
# around before/instead of a confirmed target). Consistent with this
# codebase's existing no-foreign-key style — these are plain link
# rows, not enforced FKs.

SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def _row_to_dict(row):

    return dict(row) if row is not None else None


def _resolve_target(cursor, target_id):

    cursor.execute(
        "SELECT target_id, full_name, status FROM watchlist_targets "
        "WHERE target_id = ?",
        (target_id,)
    )

    row = cursor.fetchone()

    return _row_to_dict(row)


def _resolve_unknown(cursor, unknown_id):

    cursor.execute(
        "SELECT unknown_id, status, detected_at FROM unknown_persons "
        "WHERE unknown_id = ?",
        (unknown_id,)
    )

    row = cursor.fetchone()

    return _row_to_dict(row)


def create_case(
    title,
    description=None,
    target_id=None,
    severity="MEDIUM",
    assigned_to=None,
    opened_by=None
):

    severity = (severity or "MEDIUM").upper()

    if severity not in SEVERITIES:

        raise ValueError(
            f"Unknown severity: {severity}. Must be one of "
            f"{', '.join(sorted(SEVERITIES))}."
        )

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
            severity,
            assigned_to,
            opened_by
        )
        VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?)
    """, (
        case_id,
        title,
        description,
        target_id,
        severity,
        assigned_to,
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

    # Linked targets: the case's own "primary" target_id (if set) plus
    # every row in investigation_targets, deduped and each resolved to
    # its current name/status.

    target_ids = []

    if case["target_id"]:

        target_ids.append(case["target_id"])

    cursor.execute(
        "SELECT target_id FROM investigation_targets WHERE case_id = ? "
        "ORDER BY linked_at ASC",
        (case_id,)
    )

    for row in cursor.fetchall():

        if row["target_id"] not in target_ids:

            target_ids.append(row["target_id"])

    linked_targets = [
        _resolve_target(cursor, target_id) or {
            "target_id": target_id,
            "full_name": None,
            "status": None
        }
        for target_id in target_ids
    ]

    # Linked unknown_persons sightings.

    cursor.execute(
        "SELECT unknown_id FROM investigation_unknowns WHERE case_id = ? "
        "ORDER BY linked_at ASC",
        (case_id,)
    )

    linked_unknowns = [
        _resolve_unknown(cursor, row["unknown_id"]) or {
            "unknown_id": row["unknown_id"],
            "status": None,
            "detected_at": None
        }
        for row in cursor.fetchall()
    ]

    connection.close()

    case["notes"] = notes
    case["linked_targets"] = linked_targets
    case["linked_unknowns"] = linked_unknowns

    return case


def update_case(case_id, title=None, description=None, severity=None, assigned_to=None):

    if get_case(case_id) is None:

        raise ValueError(f"Unknown case_id: {case_id}")

    fields = []
    params = []

    if title is not None:

        fields.append("title = ?")
        params.append(title)

    if description is not None:

        fields.append("description = ?")
        params.append(description)

    if severity is not None:

        severity = severity.upper()

        if severity not in SEVERITIES:

            raise ValueError(
                f"Unknown severity: {severity}. Must be one of "
                f"{', '.join(sorted(SEVERITIES))}."
            )

        fields.append("severity = ?")
        params.append(severity)

    if assigned_to is not None:

        fields.append("assigned_to = ?")
        params.append(assigned_to if assigned_to else None)

    if not fields:

        raise ValueError("No fields supplied to update.")

    params.append(case_id)

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        f"UPDATE investigations SET {', '.join(fields)} WHERE case_id = ?",
        params
    )

    connection.commit()

    connection.close()

    return get_case(case_id)


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


def link_target(case_id, target_id, linked_by=None):

    if get_case(case_id) is None:

        raise ValueError(f"Unknown case_id: {case_id}")

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute(
        "SELECT full_name FROM watchlist_targets WHERE target_id = ?",
        (target_id,)
    )

    if cursor.fetchone() is None:

        connection.close()

        raise ValueError(f"Unknown target_id: {target_id}")

    cursor.execute(
        "SELECT id FROM investigation_targets "
        "WHERE case_id = ? AND target_id = ?",
        (case_id, target_id)
    )

    if cursor.fetchone() is None:

        cursor.execute("""
            INSERT INTO investigation_targets (case_id, target_id, linked_by)
            VALUES (?, ?, ?)
        """, (case_id, target_id, linked_by))

        connection.commit()

    connection.close()

    return get_case(case_id)


def unlink_target(case_id, target_id):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM investigation_targets "
        "WHERE case_id = ? AND target_id = ?",
        (case_id, target_id)
    )

    connection.commit()

    updated = cursor.rowcount

    connection.close()

    return updated > 0


def link_unknown(case_id, unknown_id, linked_by=None):

    if get_case(case_id) is None:

        raise ValueError(f"Unknown case_id: {case_id}")

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute(
        "SELECT unknown_id FROM unknown_persons WHERE unknown_id = ?",
        (unknown_id,)
    )

    if cursor.fetchone() is None:

        connection.close()

        raise ValueError(f"Unknown unknown_id: {unknown_id}")

    cursor.execute(
        "SELECT id FROM investigation_unknowns "
        "WHERE case_id = ? AND unknown_id = ?",
        (case_id, unknown_id)
    )

    if cursor.fetchone() is None:

        cursor.execute("""
            INSERT INTO investigation_unknowns (case_id, unknown_id, linked_by)
            VALUES (?, ?, ?)
        """, (case_id, unknown_id, linked_by))

        connection.commit()

    connection.close()

    return get_case(case_id)


def unlink_unknown(case_id, unknown_id):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM investigation_unknowns "
        "WHERE case_id = ? AND unknown_id = ?",
        (case_id, unknown_id)
    )

    connection.commit()

    updated = cursor.rowcount

    connection.close()

    return updated > 0


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
