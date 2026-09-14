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
        linked_student_id TEXT,
        created_by TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        resolved_by TEXT,
        resolved_at DATETIME
    )
""")

print("✅ watchlist_targets table ready")


cursor.execute("PRAGMA table_info(watchlist_targets)")

watchlist_columns = [
    column[1]
    for column in cursor.fetchall()
]

if "linked_student_id" not in watchlist_columns:

    cursor.execute("""
        ALTER TABLE watchlist_targets
        ADD COLUMN linked_student_id TEXT
    """)

    print("✅ Added watchlist_targets.linked_student_id")

else:

    print("ℹ️ watchlist_targets.linked_student_id already exists")


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
