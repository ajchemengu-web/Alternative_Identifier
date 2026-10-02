import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking data_erasure_log table...")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS data_erasure_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        erasure_reference TEXT UNIQUE NOT NULL,
        reason TEXT NOT NULL,
        erased_by TEXT NOT NULL,
        summary TEXT NOT NULL,
        performed_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")

print("✅ data_erasure_log table ready")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
