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

existing_columns = [
    column[1]
    for column in cursor.fetchall()
]


if "false_positive" not in existing_columns:

    cursor.execute("""
        ALTER TABLE access_logs
        ADD COLUMN false_positive BOOLEAN NOT NULL DEFAULT 0
    """)

    print("✅ Added false_positive")


else:

    print("ℹ️ false_positive already exists")


if "false_positive_reason" not in existing_columns:

    cursor.execute("""
        ALTER TABLE access_logs
        ADD COLUMN false_positive_reason TEXT
    """)

    print("✅ Added false_positive_reason")


else:

    print("ℹ️ false_positive_reason already exists")


if "false_positive_reviewed_by" not in existing_columns:

    cursor.execute("""
        ALTER TABLE access_logs
        ADD COLUMN false_positive_reviewed_by TEXT
    """)

    print("✅ Added false_positive_reviewed_by")


else:

    print("ℹ️ false_positive_reviewed_by already exists")


if "false_positive_reviewed_at" not in existing_columns:

    cursor.execute("""
        ALTER TABLE access_logs
        ADD COLUMN false_positive_reviewed_at DATETIME
    """)

    print("✅ Added false_positive_reviewed_at")


else:

    print("ℹ️ false_positive_reviewed_at already exists")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
