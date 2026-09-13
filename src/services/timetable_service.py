import sqlite3

from src.db import get_connection
from src.services import unit_service


# ============================================================
# WHAT THIS IS
# ============================================================
#
# Backend for the Directorate of Timetabling Admin (docs/PRD.md §8):
# create/update/cancel timetable entries against a unit
# (unit_service.py's registry), not a facilitator name typed fresh
# onto every row. A unit already carries its own course/year/
# department/semester and (once a lecturer has claimed it) its
# lecturer_id/facilitator name — create_entry() below reads those
# once from the unit and snapshots them onto the entry, so the
# Timetabling Admin only supplies unit_id/day_of_week/start_time/
# end_time/venue per session, and a lecturer's own units can never
# drift out of sync with a typo'd name (see unit_service.py's
# docstring for why this replaced the old free-text facilitator
# match).
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


def _facilitator_name(lecturer_id):

    if not lecturer_id:

        return None

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute(
        "SELECT full_name FROM lecturers WHERE lecturer_id = ?",
        (lecturer_id,)
    )

    row = cursor.fetchone()

    connection.close()

    return row["full_name"] if row is not None else None


def create_entry(
    unit_id,
    day_of_week,
    start_time,
    end_time,
    venue,
    created_by=None
):

    day = day_of_week.upper()

    if day not in DAYS_OF_WEEK:

        raise ValueError(
            f"Unknown day_of_week: {day_of_week}"
        )

    unit = unit_service.get_unit(unit_id)

    if unit is None:

        raise ValueError(f"Unknown unit_id: {unit_id}")

    facilitator = _facilitator_name(unit["lecturer_id"])

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO timetable_entries (
            unit_id,
            unit_code,
            course,
            year,
            department,
            semester,
            lecturer_id,
            day_of_week,
            start_time,
            end_time,
            unit_name,
            facilitator,
            venue,
            status,
            created_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ON', ?)
    """, (
        unit["id"],
        unit["unit_code"],
        unit["course"],
        unit["year"],
        unit["department"],
        unit["semester"],
        unit["lecturer_id"],
        day,
        start_time,
        end_time,
        unit["unit_name"],
        facilitator,
        venue,
        created_by
    ))

    connection.commit()

    entry_id = cursor.lastrowid

    connection.close()

    return {

        "id": entry_id,

        "unit_id": unit["id"],

        "unit_code": unit["unit_code"],

        "course": unit["course"],

        "year": unit["year"],

        "department": unit["department"],

        "semester": unit["semester"],

        "lecturer_id": unit["lecturer_id"],

        "day_of_week": day,

        "start_time": start_time,

        "end_time": end_time,

        "unit_name": unit["unit_name"],

        "facilitator": facilitator,

        "venue": venue,

        "status": "ON",

        "created_by": created_by
    }


def list_entries(
    course=None,
    year=None,
    department=None,
    facilitator=None,
    semester=None,
    lecturer_id=None,
    unit_id=None
):

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

    if semester is not None:

        # Same plain match as the rest of this module — a course/
        # year's schedule commonly differs between semester 1 and
        # semester 2, so this is part of what routes an entry to the
        # right students at the right time of year (see
        # TimetableEntryRequest in src/api/main.py).
        query += " AND semester = ?"

        params.append(semester)

    if lecturer_id:

        # The current, ID-based way a lecturer's own "My Units" view
        # (docs/PRD.md §6) finds their entries — set from the unit's
        # own lecturer_id at create_entry() time above, so it can't
        # be broken by a name typo the way facilitator matching
        # could be.
        query += " AND lecturer_id = ?"

        params.append(lecturer_id)

    if unit_id is not None:

        query += " AND unit_id = ?"

        params.append(unit_id)

    if facilitator:

        # Kept for read-side compatibility (e.g. filtering the web
        # Timetabling Admin's table by name) — every entry's
        # facilitator is now derived from its unit's lecturer, not
        # typed in, but the column and this filter still work the
        # same way.
        query += " AND facilitator = ?"

        params.append(facilitator)

    query += " ORDER BY course, year, semester, day_of_week, start_time"

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
