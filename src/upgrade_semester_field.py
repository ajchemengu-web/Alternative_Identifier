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


if "semester" not in student_columns:

    cursor.execute("""
        ALTER TABLE students
        ADD COLUMN semester INTEGER
    """)

    print("✅ Added students.semester")


else:

    print("ℹ️ students.semester already exists")


print("Checking timetable_entries table...")


cursor.execute("PRAGMA table_info(timetable_entries)")

timetable_columns = [
    column[1]
    for column in cursor.fetchall()
]


if "semester" not in timetable_columns:

    cursor.execute("""
        ALTER TABLE timetable_entries
        ADD COLUMN semester INTEGER
    """)

    print("✅ Added timetable_entries.semester")


else:

    print("ℹ️ timetable_entries.semester already exists")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
