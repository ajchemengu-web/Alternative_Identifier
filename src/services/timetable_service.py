import sqlite3

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# Backend for the Directorate of Timetabling Admin (docs/PRD.md §8):
# create/update/cancel timetable entries per course and year. Entries
# are keyed by free-text course/year, matching the rest of this
# prototype's lightweight style (hostel/room on students aren't
# foreign keys either) rather than a formal course-catalog table.
#
# Scope note: this only covers the admin side (CRUD on entries).
# Actually pushing a student's own Schedule/Intraday view from these
# entries is a SmartAttendance (Flutter app) concern — out of scope
# here, since students/lecturers don't use this web platform at all
# (docs/PRD.md §4).


DAYS_OF_WEEK = {
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY"
}

STATUSES = {
    "ON",
    "POSTPONED",
    "CANCELLED"
}


def _row_to_dict(row):

    return dict(row) if row is not None else None


def create_entry(
    course,
    year,
    day_of_week,
    start_time,
    end_time,
    unit_name,
    facilitator,
    venue,
    created_by=None,
    department=None
):

    day = day_of_week.upper()

    if day not in DAYS_OF_WEEK:

        raise ValueError(
            f"Unknown day_of_week: {day_of_week}"
        )

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO timetable_entries (
            course,
            year,
            department,
            day_of_week,
            start_time,
            end_time,
            unit_name,
            facilitator,
            venue,
            status,
            created_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ON', ?)
    """, (
        course,
        year,
        department,
        day,
        start_time,
        end_time,
        unit_name,
        facilitator,
        venue,
        created_by
    ))

    connection.commit()

    connection.close()

    return {

        "course": course,

        "year": year,

        "department": department,

        "day_of_week": day,

        "start_time": start_time,

        "end_time": end_time,

        "unit_name": unit_name,

        "facilitator": facilitator,

        "venue": venue,

        "status": "ON",

        "created_by": created_by
    }


def list_entries(course=None, year=None, department=None, facilitator=None):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    query = "SELECT * FROM timetable_entries WHERE 1=1"

    params = []

    if course:

        query += " AND course = ?"

        params.append(course)

    if year is not None:

        query += " AND year = ?"

        params.append(year)

    if department:

        query += " AND department = ?"

        params.append(department)

    if facilitator:

        # Free-text match, same lightweight style as course/year/
        # department (no facilitator/lecturer foreign key) — see this
        # module's docstring. A lecturer's own "My Units" view
        # (docs/PRD.md §6) depends on their `lecturers.full_name`
        # being entered here exactly as the Timetabling Admin typed
        # it into this entry's facilitator field.
        query += " AND facilitator = ?"

        params.append(facilitator)

    query += " ORDER BY course, year, day_of_week, start_time"

    cursor.execute(query, params)

    rows = cursor.fetchall()

    connection.close()

    return [
        _row_to_dict(row)
        for row in rows
    ]


def update_status(entry_id, status):

    status = status.upper()

    if status not in STATUSES:

        raise ValueError(
            f"Unknown status: {status}"
        )

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE timetable_entries
        SET status = ?
        WHERE id = ?
    """, (
        status,
        entry_id
    ))

    connection.commit()

    updated = cursor.rowcount

    connection.close()

    return updated > 0


def delete_entry(entry_id):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM timetable_entries
        WHERE id = ?
    """, (
        entry_id,
    ))

    connection.commit()

    deleted = cursor.rowcount

    connection.close()

    return deleted > 0
