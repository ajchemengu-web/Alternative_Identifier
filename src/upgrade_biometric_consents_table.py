import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking biometric_consents table...")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS biometric_consents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        notice_version TEXT NOT NULL,
        channel TEXT NOT NULL,
        recorded_by TEXT,
        granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        withdrawn_at DATETIME
    )
""")

print("✅ biometric_consents table ready")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
