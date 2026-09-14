import sqlite3

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# The unit registry (docs/PRD.md §6, §8): a unit (e.g. "SCO 104") is
# created once by the Timetabling Admin, and a lecturer claims the
# units they teach from the app — that claim is the single source of
# truth for "who teaches this," replacing the old design where an
# admin retyped a facilitator name (free text) onto every timetable
# row. timetable_service.create_entry() reads a unit's course/year/
# department/semester/lecturer here and snapshots them onto the
# entry, so a unit only needs to be classified once, not once per
# session/week.


def _row_to_dict(row):

    return dict(row) if row is not None else None


def create_unit(
    unit_code,
    unit_name,
    course,
    year,
    semester,
    department=None,
    created_by=None
):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute("""
            INSERT INTO units (
                unit_code,
                unit_name,
                department,
                course,
                year,
                semester,
                created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            unit_code,
            unit_name,
            department,
            course,
            year,
            semester,
            created_by
        ))

        connection.commit()

        unit_id = cursor.lastrowid

    except Exception as error:

        connection.close()

        raise ValueError(
            f"Could not create unit — unit_code may already exist ({error})"
        )

    connection.close()

    return get_unit(unit_id)


def get_unit(unit_id):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM units WHERE id = ?",
        (unit_id,)
    )

    row = cursor.fetchone()

    connection.close()

    return _row_to_dict(row)


def list_units(
    department=None,
    course=None,
    year=None,
    semester=None,
    lecturer_id=None,
    unclaimed=None
):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    query = "SELECT * FROM units WHERE 1=1"

    params = []

    if department:

        query += " AND department = ?"

        params.append(department)

    if course:

        query += " AND course = ?"

        params.append(course)

    if year is not None:

        query += " AND year = ?"

        params.append(year)

    if semester is not None:

        query += " AND semester = ?"

        params.append(semester)

    if lecturer_id:

        query += " AND lecturer_id = ?"

        params.append(lecturer_id)

    if unclaimed:

        query += " AND lecturer_id IS NULL"

    query += " ORDER BY course, year, semester, unit_code"

    cursor.execute(query, params)

    rows = cursor.fetchall()

    connection.close()

    return [
        _row_to_dict(row)
        for row in rows
    ]


def claim_unit(unit_id, lecturer_id):

    # A lecturer self-registering a unit they teach. Already-claimed-
    # by-someone-else is rejected rather than silently overwritten,
    # so a genuine mistake stays visible (and fixable by an admin via
    # set_unit_lecturer) instead of two lecturers fighting over one
    # unit's lecturer_id.

    unit = get_unit(unit_id)

    if unit is None:

        raise ValueError("Unit not found")

    if unit["lecturer_id"] is not None and unit["lecturer_id"] != lecturer_id:

        raise ValueError("This unit is already claimed by another lecturer")

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        "UPDATE units SET lecturer_id = ? WHERE id = ?",
        (lecturer_id, unit_id)
    )

    connection.commit()

    connection.close()

    return get_unit(unit_id)


def unclaim_unit(unit_id, lecturer_id):

    # Lets a lecturer undo a mistaken claim. Only the lecturer who
    # holds the claim can release it — an admin uses
    # set_unit_lecturer (below) to override/reassign instead.

    unit = get_unit(unit_id)

    if unit is None:

        raise ValueError("Unit not found")

    if unit["lecturer_id"] != lecturer_id:

        raise ValueError("You have not claimed this unit")

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        "UPDATE units SET lecturer_id = NULL WHERE id = ?",
        (unit_id,)
    )

    connection.commit()

    connection.close()

    return get_unit(unit_id)


def set_unit_lecturer(unit_id, lecturer_id):

    # Admin override — no ownership check, for correcting a mistaken
    # claim or assigning a unit before its lecturer has self-
    # registered. lecturer_id=None clears the assignment back to
    # unclaimed.

    unit = get_unit(unit_id)

    if unit is None:

        raise ValueError("Unit not found")

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        "UPDATE units SET lecturer_id = ? WHERE id = ?",
        (lecturer_id, unit_id)
    )

    connection.commit()

    connection.close()

    return get_unit(unit_id)
