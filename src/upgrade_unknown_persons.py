import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


# ==========================================
# CREATE UNKNOWN PERSONS TABLE
# ==========================================

cursor.execute("""
    CREATE TABLE IF NOT EXISTS unknown_persons (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        unknown_id TEXT UNIQUE NOT NULL,

        image_path TEXT NOT NULL,

        status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',

        detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,

        reviewed_at DATETIME,

        reviewed_by TEXT

    )
""")


connection.commit()

connection.close()


print("✅ Unknown persons table created successfully!")