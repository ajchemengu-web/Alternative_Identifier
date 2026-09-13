import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking students table...")


cursor.execute("PRAGMA table_info(students)")

student_columns = [
    column[1]
    for column in cursor.fetchall()
]


if "department" not in student_columns:

    cursor.execute("""
        ALTER TABLE students
        ADD COLUMN department TEXT
    """)

    print("✅ Added students.department")


else:

    print("ℹ️ students.department already exists")


if "course" not in student_columns:

    cursor.execute("""
        ALTER TABLE students
        ADD COLUMN course TEXT
    """)

    print("✅ Added students.course")


else:

    print("ℹ️ students.course already exists")


if "year" not in student_columns:

    cursor.execute("""
        ALTER TABLE students
        ADD COLUMN year INTEGER
    """)

    print("✅ Added students.year")


else:

    print("ℹ️ students.year already exists")


print("Checking timetable_entries table...")


cursor.execute("PRAGMA table_info(timetable_entries)")

timetable_columns = [
    column[1]
    for column in cursor.fetchall()
]


if "department" not in timetable_columns:

    cursor.execute("""
        ALTER TABLE timetable_entries
        ADD COLUMN department TEXT
    """)

    print("✅ Added timetable_entries.department")


else:

    print("ℹ️ timetable_entries.department already exists")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
