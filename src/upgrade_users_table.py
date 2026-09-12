import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking users table...")


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

print("✅ users table ready")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
