import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking cameras table...")


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

print("✅ cameras table ready")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
