import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking guests table...")


# Get existing columns
cursor.execute("PRAGMA table_info(guests)")

columns = cursor.fetchall()

existing_columns = [
    column[1]
    for column in columns
]


# Add embedding_file if missing
if "embedding_file" not in existing_columns:

    cursor.execute("""
        ALTER TABLE guests
        ADD COLUMN embedding_file TEXT
    """)

    print("✅ Added embedding_file")


else:

    print("ℹ️ embedding_file already exists")


# Add rejected_by if missing
if "rejected_by" not in existing_columns:

    cursor.execute("""
        ALTER TABLE guests
        ADD COLUMN rejected_by TEXT
    """)

    print("✅ Added rejected_by")


else:

    print("ℹ️ rejected_by already exists")


# Add rejected_at if missing
if "rejected_at" not in existing_columns:

    cursor.execute("""
        ALTER TABLE guests
        ADD COLUMN rejected_at DATETIME
    """)

    print("✅ Added rejected_at")


else:

    print("ℹ️ rejected_at already exists")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")