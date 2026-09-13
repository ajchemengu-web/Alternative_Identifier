import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking lecturers table...")


cursor.execute("""
    CREATE TABLE IF NOT EXISTS lecturers (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        lecturer_id TEXT UNIQUE NOT NULL,

        full_name TEXT NOT NULL,

        department TEXT,

        created_at DATETIME DEFAULT CURRENT_TIMESTAMP

    )
""")

print("✅ lecturers table ready")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
