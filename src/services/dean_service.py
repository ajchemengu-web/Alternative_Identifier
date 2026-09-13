import sqlite3

from src.db import get_connection
from src.services import timetable_service


# ============================================================
# WHAT THIS IS
# ============================================================
#
# Backend for the Dean of School Admin's dashboard (docs/PRD.md §8):
# "Per-school scope: class logs, venue camera access, total student
# roster by classification, total lectures/units for the department,
# access to all department timetables."
#
# Scope note: only the two pieces with data to back them are built
# here — the student roster (grouped by course/year, docs/PRD.md
# §8's "classification") and the department's timetable/unit totals,
# both scoped by the free-text `department` field on `students` and
# `timetable_entries` (same lightweight, no-foreign-key style as the
# rest of this prototype — see timetable_service.py).
#
# "Class logs" (per-lecture attendance) and "venue camera access"
# depend on the SmartAttendance classroom-camera pipeline and camera
# management, neither of which exist in this backend yet — out of
# scope here until that infrastructure is built.


def _row_to_dict(row):

    return dict(row) if row is not None else None


def get_roster(department=None):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    if department:

        cursor.execute("""
            SELECT
                student_id,
                full_name,
                admission_number,
                department,
                course,
                year
            FROM students
            WHERE department = ?
            ORDER BY course, year, full_name
        """, (department,))

    else:

        cursor.execute("""
            SELECT
                student_id,
                full_name,
                admission_number,
                department,
                course,
                year
            FROM students
            ORDER BY course, year, full_name
        """)

    rows = cursor.fetchall()

    connection.close()

    return [
        _row_to_dict(row)
        for row in rows
    ]


def get_classification_summary(department=None):

    roster = get_roster(department)

    counts = {}

    for student in roster:

        key = (student["course"], student["year"])

        counts[key] = counts.get(key, 0) + 1

    return [
        {
            "course": course,
            "year": year,
            "student_count": count
        }
        for (course, year), count in sorted(
            counts.items(),
            key=lambda item: (
                item[0][0] or "",
                item[0][1] or 0
            )
        )
    ]


def get_summary(department=None):

    roster = get_roster(department)

    timetable_entries = timetable_service.list_entries(
        department=department
    )

    active_entries = [
        entry
        for entry in timetable_entries
        if entry["status"] == "ON"
    ]

    unit_names = {
        entry["unit_name"]
        for entry in timetable_entries
    }

    return {

        "department": department,

        "total_students": len(roster),

        "roster_by_classification": get_classification_summary(
            department
        ),

        "total_units": len(unit_names),

        "total_active_lectures": len(active_entries),

        "total_timetable_entries": len(timetable_entries)
    }
