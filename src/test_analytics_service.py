import os
import sqlite3
import tempfile
from datetime import datetime, timedelta


def _create_schema(path):

    connection = sqlite3.connect(path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_type TEXT NOT NULL,
            person_identifier TEXT,
            entrance TEXT,
            recognition_score REAL,
            decision TEXT,
            guard_id TEXT,
            liveness_score REAL,
            false_positive BOOLEAN NOT NULL DEFAULT 0,
            false_positive_reason TEXT,
            false_positive_reviewed_by TEXT,
            false_positive_reviewed_at DATETIME,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


def _insert_log(
    connection,
    person_type,
    entrance,
    decision,
    recognition_score=None,
    liveness_score=None,
    timestamp=None
):

    connection.execute("""
        INSERT INTO access_logs (
            person_type, person_identifier, entrance, decision,
            recognition_score, liveness_score, timestamp
        )
        VALUES (?, 'P1', ?, ?, ?, ?, ?)
    """, (
        person_type, entrance, decision, recognition_score,
        liveness_score, (timestamp or datetime.now()).isoformat()
    ))


if __name__ == "__main__":

    print("Testing analytics_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    now = datetime.now()

    connection = sqlite3.connect(temp_db_path)

    _insert_log(connection, "STUDENT", "Main Gate", "VERIFIED", 0.92, 0.81, now)
    _insert_log(connection, "STUDENT", "Main Gate", "VERIFIED", 0.88, 0.79, now)
    _insert_log(connection, "GUEST", "Main Gate", "AG_VALID", None, None, now)
    _insert_log(connection, "STUDENT", "Side Gate", "LIVENESS_FAILED", 0.60, 0.20, now)
    _insert_log(
        connection, "STUDENT", "Main Gate", "VERIFIED", 0.55, 0.70,
        now - timedelta(days=10)
    )

    connection.commit()
    connection.close()

    from src.services import analytics_service

    # ------------------------------------------------------------
    # SUMMARY — no date filter
    # ------------------------------------------------------------

    summary = analytics_service.get_summary()

    assert summary["total_access_attempts"] == 5
    assert summary["counts_by_decision"] == {
        "VERIFIED": 3,
        "AG_VALID": 1,
        "LIVENESS_FAILED": 1
    }
    assert summary["movement_by_entrance"] == {
        "Main Gate": 4,
        "Side Gate": 1
    }
    assert summary["movement_by_person_type"] == {
        "STUDENT": 4,
        "GUEST": 1
    }
    assert summary["verified_count"] == 3
    assert summary["false_positive_count"] == 0
    assert summary["false_positive_rate"] == 0.0
    print("Summary (unfiltered) ->", summary)

    # ------------------------------------------------------------
    # SUMMARY — date filtered (last 7 days excludes the 10-day-old row)
    # ------------------------------------------------------------

    recent_summary = analytics_service.get_summary(
        since=now - timedelta(days=7)
    )
    assert recent_summary["total_access_attempts"] == 4
    assert recent_summary["verified_count"] == 2
    print("Summary (last 7 days) ->", recent_summary)

    # ------------------------------------------------------------
    # FLAG FALSE POSITIVE
    # ------------------------------------------------------------

    connection = sqlite3.connect(temp_db_path)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute(
        "SELECT id FROM access_logs WHERE decision = 'VERIFIED' "
        "ORDER BY timestamp DESC LIMIT 1"
    )
    target_id = cursor.fetchone()["id"]
    connection.close()

    flagged = analytics_service.flag_false_positive(
        target_id,
        "Guard confirmed this was a different student on review footage",
        "guard1"
    )
    assert flagged is True
    print(f"Flagged access_log id={target_id} as a false positive")

    missing_flag = analytics_service.flag_false_positive(
        99999, "irrelevant", "guard1"
    )
    assert missing_flag is False
    print("Flagging a non-existent access_log id returns False, as expected")

    updated_summary = analytics_service.get_summary()
    assert updated_summary["false_positive_count"] == 1
    assert updated_summary["false_positive_rate"] == 1 / 3
    print("Updated summary reflects the flagged false positive ->", updated_summary)

    # ------------------------------------------------------------
    # EMPTY DATABASE (no rows at all yet)
    # ------------------------------------------------------------

    empty_dir = tempfile.mkdtemp()
    empty_db_path = os.path.join(empty_dir, "empty.db")
    _create_schema(empty_db_path)
    db.DATABASE_PATH = empty_db_path

    empty_summary = analytics_service.get_summary()
    assert empty_summary["total_access_attempts"] == 0
    assert empty_summary["false_positive_rate"] is None
    assert empty_summary["average_recognition_score"] is None
    print("Empty-database summary handled without dividing by zero ->", empty_summary)

    import shutil
    shutil.rmtree(temp_dir)
    shutil.rmtree(empty_dir)

    print("\nanalytics_service smoke test passed.")
