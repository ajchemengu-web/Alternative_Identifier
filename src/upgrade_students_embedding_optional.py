import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking students.embedding_file...")


cursor.execute("PRAGMA table_info(students)")

embedding_column = next(
    (column for column in cursor.fetchall() if column[1] == "embedding_file"),
    None
)

# column tuple: (cid, name, type, notnull, dflt_value, pk) — notnull=1
# means the constraint is still there. SQLite has no ALTER COLUMN to
# drop it, so the table has to be rebuilt (same dance SQLite's own
# docs recommend for this kind of schema change).
if embedding_column is not None and embedding_column[3] == 1:

    cursor.execute("ALTER TABLE students RENAME TO students_old")

    cursor.execute("""
        CREATE TABLE students (

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

            embedding_file TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP

        )
    """)

    cursor.execute("""
        INSERT INTO students (
            id, student_id, full_name, admission_number, hostel, room,
            department, course, year, semester, embedding_file, created_at
        )
        SELECT
            id, student_id, full_name, admission_number, hostel, room,
            department, course, year, semester, embedding_file, created_at
        FROM students_old
    """)

    cursor.execute("DROP TABLE students_old")

    print("✅ students.embedding_file is now nullable")


else:

    print("ℹ️ students.embedding_file is already nullable")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
