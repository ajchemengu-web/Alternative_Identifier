import sqlite3
import os
from datetime import datetime


DATABASE_PATH = os.path.join(
    "data",
    "smarthostel.db"
)


def log_access(
    person_type,
    person_identifier,
    entrance="Nyayo Main Gate",
    recognition_score=None,
    decision="VERIFIED",
    guard_id=None
):

    connection = sqlite3.connect(DATABASE_PATH)

    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO access_logs (
            person_type,
            person_identifier,
            entrance,
            recognition_score,
            decision,
            guard_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        person_type,
        person_identifier,
        entrance,
        recognition_score,
        decision,
        guard_id
    ))

    connection.commit()

    connection.close()

    print(
        f" ACCESS LOGGED → "
        f"{person_type}: {person_identifier}"
    )


if __name__ == "__main__":

    print("Testing access logger...")

    log_access(
        person_type="TEST",
        person_identifier="TEST-001"
    )

    print("Test log created!")