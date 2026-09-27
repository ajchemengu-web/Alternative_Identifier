import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking class_sessions table...")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS class_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timetable_entry_id INTEGER NOT NULL,
        session_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        activates_at DATETIME NOT NULL,
        cutoff_at DATETIME NOT NULL,
        submit_at DATETIME NOT NULL,
        submitted_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (timetable_entry_id, session_date)
    )
""")

print("✅ class_sessions table ready")


print("Checking attendance_records table...")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_session_id INTEGER NOT NULL,
        student_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ABSENT',
        recognized_at DATETIME,
        recognition_score REAL,
        UNIQUE (class_session_id, student_id)
    )
""")

print("✅ attendance_records table ready")


print("Checking attendance_notifications table...")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        class_session_id INTEGER NOT NULL,
        kind TEXT NOT NULL,
        unit_name TEXT NOT NULL,
        facilitator TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        read_at DATETIME
    )
""")

print("✅ attendance_notifications table ready")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
