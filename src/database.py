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

        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """)


    connection.commit()

    connection.close()

    print(" Database initialized successfully!")


if __name__ == "__main__":

    initialize_database()