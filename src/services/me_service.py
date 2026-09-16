import sqlite3

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# Backend for the SmartAttendance app's "my own profile" lookup
# (docs/PRD.md §6, Phase 2): a STUDENT or LECTURER only gets a bare
# username/role/admin_tier from their JWT
# (src/services/auth_service.py) — this resolves that to the actual
# student/lecturer record via users.linked_person_id, so the app
# knows what to request a timetable for (a student's
# department/course/year/semester, a lecturer's own name to match
# against timetable_entries.facilitator — see timetable_service.py's
# list_entries filters).


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
            year,
            semester
        FROM students
        WHERE student_id = ?
    """, (
        student_id,
    ))

    student_row = cursor.fetchone()

    connection.close()

    return dict(student_row) if student_row is not None else None


def get_my_lecturer_profile(username):

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

    lecturer_id = user_row["linked_person_id"]

    cursor.execute("""
        SELECT
            lecturer_id,
            full_name,
            department
        FROM lecturers
        WHERE lecturer_id = ?
    """, (
        lecturer_id,
    ))

    lecturer_row = cursor.fetchone()

    connection.close()

    return dict(lecturer_row) if lecturer_row is not None else None
