import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking timetable_entries table...")


cursor.execute("""
    CREATE TABLE IF NOT EXISTS timetable_entries (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        course TEXT NOT NULL,

        year INTEGER NOT NULL,

        day_of_week TEXT NOT NULL,

        start_time TEXT NOT NULL,

        end_time TEXT NOT NULL,

        unit_name TEXT NOT NULL,

        facilitator TEXT NOT NULL,

        venue TEXT NOT NULL,

        status TEXT NOT NULL DEFAULT 'ON',

        created_by TEXT,

        created_at DATETIME DEFAULT CURRENT_TIMESTAMP

    )
""")

print("✅ timetable_entries table ready")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
