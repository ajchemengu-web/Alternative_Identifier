import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking watchlist_targets table...")


cursor.execute("""
    CREATE TABLE IF NOT EXISTS watchlist_targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_id TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        description TEXT,
        reason TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        embedding_file TEXT,
        created_by TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        resolved_by TEXT,
        resolved_at DATETIME
    )
""")

print("✅ watchlist_targets table ready")


print("Checking investigations table...")


cursor.execute("""
    CREATE TABLE IF NOT EXISTS investigations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        target_id TEXT,
        status TEXT NOT NULL DEFAULT 'OPEN',
        opened_by TEXT,
        opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        closed_by TEXT,
        closed_at DATETIME
    )
""")

print("✅ investigations table ready")


print("Checking investigation_notes table...")


cursor.execute("""
    CREATE TABLE IF NOT EXISTS investigation_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT NOT NULL,
        author TEXT,
        note TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")

print("✅ investigation_notes table ready")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
