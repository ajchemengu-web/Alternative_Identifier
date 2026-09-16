import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking access_logs table...")


cursor.execute("PRAGMA table_info(access_logs)")

access_logs_columns = [
    column[1]
    for column in cursor.fetchall()
]

if "alert_acknowledged" not in access_logs_columns:

    cursor.execute("""
        ALTER TABLE access_logs
        ADD COLUMN alert_acknowledged BOOLEAN NOT NULL DEFAULT 0
    """)

    print("✅ Added access_logs.alert_acknowledged")

else:

    print("ℹ️ access_logs.alert_acknowledged already exists")

if "alert_acknowledged_by" not in access_logs_columns:

    cursor.execute("""
        ALTER TABLE access_logs
        ADD COLUMN alert_acknowledged_by TEXT
    """)

    print("✅ Added access_logs.alert_acknowledged_by")

else:

    print("ℹ️ access_logs.alert_acknowledged_by already exists")

if "alert_acknowledged_at" not in access_logs_columns:

    cursor.execute("""
        ALTER TABLE access_logs
        ADD COLUMN alert_acknowledged_at DATETIME
    """)

    print("✅ Added access_logs.alert_acknowledged_at")

else:

    print("ℹ️ access_logs.alert_acknowledged_at already exists")


print("Checking investigations table...")


cursor.execute("PRAGMA table_info(investigations)")

investigations_columns = [
    column[1]
    for column in cursor.fetchall()
]

if "severity" not in investigations_columns:

    cursor.execute("""
        ALTER TABLE investigations
        ADD COLUMN severity TEXT NOT NULL DEFAULT 'MEDIUM'
    """)

    print("✅ Added investigations.severity")

else:

    print("ℹ️ investigations.severity already exists")

if "assigned_to" not in investigations_columns:

    cursor.execute("""
        ALTER TABLE investigations
        ADD COLUMN assigned_to TEXT
    """)

    print("✅ Added investigations.assigned_to")

else:

    print("ℹ️ investigations.assigned_to already exists")


print("Checking investigation_targets table...")


cursor.execute("""
    CREATE TABLE IF NOT EXISTS investigation_targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        linked_by TEXT,
        linked_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")

print("✅ investigation_targets table ready")


print("Checking investigation_unknowns table...")


cursor.execute("""
    CREATE TABLE IF NOT EXISTS investigation_unknowns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT NOT NULL,
        unknown_id TEXT NOT NULL,
        linked_by TEXT,
        linked_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")

print("✅ investigation_unknowns table ready")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
