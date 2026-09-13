import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking units table...")


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

print("✅ units table ready")


print("Checking timetable_entries table...")


cursor.execute("PRAGMA table_info(timetable_entries)")

timetable_columns = [
    column[1]
    for column in cursor.fetchall()
]


if "unit_id" not in timetable_columns:

    cursor.execute("""
        ALTER TABLE timetable_entries
        ADD COLUMN unit_id INTEGER
    """)

    print("✅ Added timetable_entries.unit_id")


else:

    print("ℹ️ timetable_entries.unit_id already exists")


if "unit_code" not in timetable_columns:

    cursor.execute("""
        ALTER TABLE timetable_entries
        ADD COLUMN unit_code TEXT
    """)

    print("✅ Added timetable_entries.unit_code")


else:

    print("ℹ️ timetable_entries.unit_code already exists")


if "lecturer_id" not in timetable_columns:

    cursor.execute("""
        ALTER TABLE timetable_entries
        ADD COLUMN lecturer_id TEXT
    """)

    print("✅ Added timetable_entries.lecturer_id")


else:

    print("ℹ️ timetable_entries.lecturer_id already exists")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
