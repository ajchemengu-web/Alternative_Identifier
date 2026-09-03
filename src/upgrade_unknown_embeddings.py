import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)
cursor = connection.cursor()


# ==========================================
# CHECK EXISTING COLUMNS
# ==========================================

cursor.execute(
    "PRAGMA table_info(unknown_persons)"
)

columns = [
    row[1]
    for row in cursor.fetchall()
]


# ==========================================
# ADD EMBEDDING FILE COLUMN
# ==========================================

if "embedding_file" not in columns:

    cursor.execute("""
        ALTER TABLE unknown_persons
        ADD COLUMN embedding_file TEXT
    """)

    print("✅ embedding_file column added.")

else:

    print("ℹ️ embedding_file already exists.")


connection.commit()
connection.close()


print("✅ Unknown persons database upgraded successfully!")