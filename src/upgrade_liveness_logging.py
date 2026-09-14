import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking access_logs table...")


# Get existing columns
cursor.execute("PRAGMA table_info(access_logs)")

columns = cursor.fetchall()

existing_columns = [
    column[1]
    for column in columns
]


# Add liveness_score if missing
if "liveness_score" not in existing_columns:

    cursor.execute("""
        ALTER TABLE access_logs
        ADD COLUMN liveness_score REAL
    """)

    print("✅ Added liveness_score")


else:

    print("ℹ️ liveness_score already exists")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
