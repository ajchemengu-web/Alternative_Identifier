import os
import sqlite3
import tempfile


def _create_schema(path):

    connection = sqlite3.connect(path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
        )
    """)

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
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            alert_acknowledged BOOLEAN NOT NULL DEFAULT 0,
            alert_acknowledged_by TEXT,
            alert_acknowledged_at DATETIME
        )
    """)

    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing alerts_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    connection = sqlite3.connect(temp_db_path)
    connection.execute(
        "INSERT INTO watchlist_targets (target_id, full_name, reason) "
        "VALUES ('TGT-1', 'Person Of Interest', 'Reported theft')"
    )
    connection.execute("""
        INSERT INTO access_logs (person_type, person_identifier, entrance, decision)
        VALUES ('TARGET', 'TGT-1', 'Main Gate', 'TARGET_ALERT')
    """)
    connection.execute("""
        INSERT INTO access_logs (person_type, person_identifier, entrance, decision)
        VALUES ('TARGET', 'TGT-1', 'Side Gate', 'TARGET_ALERT')
    """)
    # Not a target alert — must never show up in the pending queue.
    connection.execute("""
        INSERT INTO access_logs (person_type, person_identifier, entrance, decision)
        VALUES ('STUDENT', 'STU-1', 'Main Gate', 'VERIFIED')
    """)
    connection.commit()
    connection.close()

    from src.services import alerts_service

    # ------------------------------------------------------------
    # LIST PENDING — every unacknowledged TARGET_ALERT, newest first
    # ------------------------------------------------------------

    pending = alerts_service.list_pending_alerts()
    assert len(pending) == 2
    assert all(alert["decision"] == "TARGET_ALERT" for alert in pending)
    assert pending[0]["full_name"] == "Person Of Interest"
    assert pending[0]["reason"] == "Reported theft"
    print("Pending target alerts ->", pending)

    # ------------------------------------------------------------
    # ACKNOWLEDGE — removes it from the pending queue
    # ------------------------------------------------------------

    first_alert_id = pending[-1]["id"]  # oldest of the two (Main Gate)

    acknowledged = alerts_service.acknowledge_alert(first_alert_id, "security1")
    assert acknowledged is True

    still_pending = alerts_service.list_pending_alerts()
    assert len(still_pending) == 1
    assert still_pending[0]["entrance"] == "Side Gate"
    print("Acknowledged one alert; the other remains pending ->", still_pending)

    connection = sqlite3.connect(temp_db_path)
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT * FROM access_logs WHERE id = ?", (first_alert_id,)
    ).fetchone()
    connection.close()
    assert row["alert_acknowledged"] == 1
    assert row["alert_acknowledged_by"] == "security1"
    assert row["alert_acknowledged_at"] is not None
    print("Acknowledged row persisted correctly ->", dict(row))

    missing_ack = alerts_service.acknowledge_alert(9999, "security1")
    assert missing_ack is False
    print("Acknowledging a non-existent alert returns False, as expected")

    reack = alerts_service.acknowledge_alert(first_alert_id, "security1")
    assert reack is False
    print("Re-acknowledging an already-acknowledged alert returns False, as expected")

    import shutil
    shutil.rmtree(temp_dir)

    print("\nalerts_service smoke test passed.")
