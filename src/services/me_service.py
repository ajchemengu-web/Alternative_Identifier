import sqlite3

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# Backend for the SmartAttendance app's "my own profile" lookup
# (docs/PRD.md §6, Phase 2): a STUDENT only gets a bare username/
# role/admin_tier from their JWT (src/services/auth_service.py) —
# this resolves that to the actual student record via
# users.linked_person_id, so the app knows which course/year to
# request a timetable for.
#
# LECTURER isn't covered yet: there is no lecturer table (only
# `students` has course/year/department columns) — deferred rather
# than guessed at.


def get_my_student_profile(username):

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

        return None

    student_id = user_row["linked_person_id"]

    cursor.execute("""
        SELECT
            student_id,
            full_name,
            admission_number,
            department,
            course,
            year
        FROM students
        WHERE student_id = ?
    """, (
        student_id,
    ))

    student_row = cursor.fetchone()

    connection.close()

    return dict(student_row) if student_row is not None else None
