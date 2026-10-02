import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking audit_log table...")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        occurred_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        times INTEGER NOT NULL DEFAULT 1,
        username TEXT NOT NULL,
        role TEXT,
        admin_tier TEXT,
        department TEXT,
        action TEXT NOT NULL,
        subject_id TEXT NOT NULL DEFAULT '',
        params TEXT NOT NULL DEFAULT '{}'
    )
""")

cursor.execute("""
    CREATE INDEX IF NOT EXISTS audit_log_user_idx
    ON audit_log (username, occurred_at)
""")

cursor.execute("""
    CREATE INDEX IF NOT EXISTS audit_log_subject_idx
    ON audit_log (subject_id, occurred_at)
""")

print("✅ audit_log table ready")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
