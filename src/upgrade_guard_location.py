import sqlite3
import os


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


connection = sqlite3.connect(DATABASE_PATH)

cursor = connection.cursor()


print("Checking users table...")


cursor.execute("PRAGMA table_info(users)")

user_columns = [
    column[1]
    for column in cursor.fetchall()
]


if "location" not in user_columns:

    cursor.execute("""
        ALTER TABLE users
        ADD COLUMN location TEXT
    """)

    print("✅ Added users.location")


else:

    print("ℹ️ users.location already exists")


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
