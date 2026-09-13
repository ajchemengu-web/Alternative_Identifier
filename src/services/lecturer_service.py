import sqlite3

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# A lecturer profile registry — full_name/department, no facial
# embedding (docs/PRD.md §5's enrollment_service.py already flags
# that lecturer/staff/guard facial enrollment needs its own table
# before it can be wired up; this is that table, minus the facial
# part, since SmartAttendance's "My Units" view only needs a name to
# match against timetable_entries.facilitator, not a face template).
#
# An Original/Security Admin creates a lecturer record here first,
# then references its lecturer_id as the `linked_person_id` when
# enrolling that person's LECTURER login via POST /enroll — same
# two-step shape as a student (students row exists, then /enroll
# creates the login referencing it via linked_person_id).


def _row_to_dict(row):

    return dict(row) if row is not None else None


def create_lecturer(lecturer_id, full_name, department=None):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute("""
            INSERT INTO lecturers (
                lecturer_id,
                full_name,
                department
            )
            VALUES (?, ?, ?)
        """, (
            lecturer_id,
            full_name,
            department
        ))

        connection.commit()

    except Exception as error:

        connection.close()

        raise ValueError(
            f"Could not create lecturer — lecturer_id may already "
            f"exist ({error})"
        )

    connection.close()

    return {

        "lecturer_id": lecturer_id,

        "full_name": full_name,

        "department": department
    }


def list_lecturers(department=None):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    if department:

        cursor.execute("""
            SELECT lecturer_id, full_name, department
            FROM lecturers
            WHERE department = ?
            ORDER BY full_name
        """, (department,))

    else:

        cursor.execute("""
            SELECT lecturer_id, full_name, department
            FROM lecturers
            ORDER BY full_name
        """)

    rows = cursor.fetchall()

    connection.close()

    return [
        _row_to_dict(row)
        for row in rows
    ]
