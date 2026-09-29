import os
import sqlite3
import tempfile


def _create_schema(path):

    connection = sqlite3.connect(path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS biometric_consents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            notice_version TEXT NOT NULL,
            channel TEXT NOT NULL,
            recorded_by TEXT,
            granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            withdrawn_at DATETIME
        )
    """)

    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing consent_service...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    from src.services import consent_service

    # The notice carries its version and every section the client
    # needs to render — served by the API so clients can't drift from
    # what was recorded.
    notice = consent_service.get_notice()
    assert notice["version"] == consent_service.NOTICE_VERSION
    headings = [section["heading"] for section in notice["sections"]]
    assert "Your choice and your rights" in headings
    assert "How long we keep it" in headings
    print("Notice sections ->", headings)

    # Controller/contact come from the environment so each institution
    # names itself rather than shipping with a placeholder identity.
    os.environ["CONSENT_CONTROLLER_NAME"] = "Example University"
    os.environ["CONSENT_CONTACT"] = "dpo@example.ac.ke"
    notice = consent_service.get_notice()
    assert notice["controller"] == "Example University"
    assert notice["contact"] == "dpo@example.ac.ke"
    print("Controller/contact overridable via env -> ok")

    # Fresh student: nothing recorded, not "needs re-consent".
    status = consent_service.get_status("S1")
    assert status["consent_active"] is False
    assert status["needs_reconsent"] is False
    print("Fresh student status ->", status)

    # Grant, then it's active with its channel/version.
    status = consent_service.record_consent("S1", "SELF", recorded_by="s1.user")
    assert status["consent_active"] is True
    assert status["channel"] == "SELF"
    assert status["notice_version"] == consent_service.NOTICE_VERSION
    print("After granting ->", status)

    # Withdraw: no longer active; reports whether anything changed.
    assert consent_service.withdraw_consent("S1") is True
    assert consent_service.has_active_consent("S1") is False
    assert consent_service.withdraw_consent("S1") is False
    print("Withdrawal deactivates consent; repeating is a no-op -> ok")

    # Granting again after withdrawal starts a NEW row (history kept).
    consent_service.record_consent("S1", "SELF")
    connection = sqlite3.connect(temp_db_path)
    total = connection.execute(
        "SELECT COUNT(*) FROM biometric_consents WHERE student_id = 'S1'"
    ).fetchone()[0]
    connection.close()
    assert total == 2
    print("Re-consent after withdrawal keeps the audit history (2 rows) -> ok")

    # Consent for one student never counts for another.
    assert consent_service.has_active_consent("S2") is False

    import shutil
    shutil.rmtree(temp_dir)

    print("\nconsent_service smoke test passed.")
