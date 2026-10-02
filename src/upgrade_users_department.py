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


if "department" not in user_columns:

    cursor.execute("""
        ALTER TABLE users
        ADD COLUMN department TEXT
    """)

    print("✅ Added users.department")


else:

    print("ℹ️ users.department already exists")


# A Dean account created before this column existed has no department,
# so the server refuses it Dean data (fail closed). Say so, rather than
# leaving it to be discovered at login.
cursor.execute("""
    SELECT username
    FROM users
    WHERE role = 'ADMIN'
    AND admin_tier = 'DEAN'
    AND (department IS NULL OR TRIM(department) = '')
""")

for (username,) in cursor.fetchall():

    print(
        f"⚠️ Dean account '{username}' has no department — set one "
        "(UPDATE users SET department = '...' WHERE username = '...') "
        "or it will be refused Dean data."
    )


connection.commit()

connection.close()


print("\n🎉 Database upgrade complete!")
