import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


def get_connection():

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    return connection


def initialize_database():

    connection = get_connection()

    cursor = connection.cursor()


    # =========================================
    # STUDENTS TABLE
    # =========================================

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        student_id TEXT UNIQUE NOT NULL,

        full_name TEXT NOT NULL,

        admission_number TEXT UNIQUE NOT NULL,

        hostel TEXT NOT NULL,

        room TEXT NOT NULL,

        department TEXT,

        course TEXT,

        year INTEGER,

        semester INTEGER,

        embedding_file TEXT NOT NULL,

        created_at DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """)


    # =========================================
    # GUESTS TABLE
    # =========================================

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guests (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        guest_id TEXT UNIQUE NOT NULL,

        photo_path TEXT,

        status TEXT NOT NULL,

        admitted_by TEXT,

        admitted_at DATETIME,

        expires_at DATETIME,

        created_at DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """)


    # =========================================
    # USERS TABLE (Enrollment Dashboard, docs/PRD.md §5)
    # =========================================

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT UNIQUE NOT NULL,

        password_hash TEXT NOT NULL,

        email TEXT UNIQUE NOT NULL,

        role TEXT NOT NULL,

        admin_tier TEXT,

        linked_person_id TEXT,

        temp_expires_at DATETIME,

        is_active INTEGER NOT NULL DEFAULT 1,

        created_at DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """)


    # =========================================
    # ACCESS LOGS TABLE
    # =========================================

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS access_logs (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        person_type TEXT NOT NULL,

        person_identifier TEXT,

        entrance TEXT,

        recognition_score REAL,

        decision TEXT,

        guard_id TEXT,

        liveness_score REAL,

        false_positive BOOLEAN NOT NULL DEFAULT 0,

        false_positive_reason TEXT,

        false_positive_reviewed_by TEXT,

        false_positive_reviewed_at DATETIME,

        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """)


    # =========================================
    # UNITS TABLE (unit registry — docs/PRD.md
    # §6, §8: a unit has exactly one assigned
    # lecturer, set by that lecturer claiming
    # it, not by an admin typing a facilitator
    # name onto every timetable row)
    # =========================================

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS units (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        unit_code TEXT UNIQUE NOT NULL,

        unit_name TEXT NOT NULL,

        department TEXT,

        course TEXT NOT NULL,

        year INTEGER NOT NULL,

        semester INTEGER NOT NULL,

        lecturer_id TEXT,

        created_by TEXT,

        created_at DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """)


    # =========================================
    # TIMETABLE ENTRIES TABLE (Directorate of
    # Timetabling Admin, docs/PRD.md §8). Each
    # entry references a unit (unit_id); the
    # unit's own course/year/department/
    # semester/unit_name/lecturer are snapshot
    # onto the entry at creation time so every
    # existing reader (student schedule, Dean
    # summary, analytics) keeps working off
    # plain columns without a join.
    # =========================================

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS timetable_entries (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        unit_id INTEGER,

        unit_code TEXT,

        course TEXT NOT NULL,

        year INTEGER NOT NULL,

        department TEXT,

        semester INTEGER,

        lecturer_id TEXT,

        day_of_week TEXT NOT NULL,

        start_time TEXT NOT NULL,

        end_time TEXT NOT NULL,

        unit_name TEXT NOT NULL,

        facilitator TEXT,

        venue TEXT NOT NULL,

        status TEXT NOT NULL DEFAULT 'ON',

        created_by TEXT,

        created_at DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """)


    # =========================================
    # CAMERAS TABLE (Original Admin "camera
    # management control", Security Admin
    # "camera access/configuration within
    # SmartAccess", Dean "venue camera access" —
    # docs/PRD.md §8)
    # =========================================

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cameras (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        camera_id TEXT UNIQUE NOT NULL,

        name TEXT NOT NULL,

        camera_type TEXT NOT NULL,

        location TEXT,

        department TEXT,

        source TEXT,

        status TEXT NOT NULL DEFAULT 'OFFLINE',

        enabled BOOLEAN NOT NULL DEFAULT 1,

        created_by TEXT,

        created_at DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """)


    # =========================================
    # LECTURERS TABLE (SmartAttendance's "my own
    # units" lookup, docs/PRD.md §6, Phase 2)
    # =========================================

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lecturers (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        lecturer_id TEXT UNIQUE NOT NULL,

        full_name TEXT NOT NULL,

        department TEXT,

        created_at DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """)


    connection.commit()

    connection.close()

    print(" Database initialized successfully!")


if __name__ == "__main__":

    initialize_database()