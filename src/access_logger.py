from datetime import datetime

from src.db import get_connection


def log_access(
    person_type,
    person_identifier,
    entrance="Nyayo Main Gate",
    recognition_score=None,
    decision="VERIFIED",
    guard_id=None,
    liveness_score=None
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO access_logs (
            person_type,
            person_identifier,
            entrance,
            recognition_score,
            decision,
            guard_id,
            liveness_score
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        person_type,
        person_identifier,
        entrance,
        recognition_score,
        decision,
        guard_id,
        liveness_score
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