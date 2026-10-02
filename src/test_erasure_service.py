import os
import sqlite3
import tempfile

import numpy as np

from src.test_enrollment_service import _install_fake_insightface


def _create_schema(path):

    connection = sqlite3.connect(path)

    connection.executescript("""
        CREATE TABLE students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            admission_number TEXT UNIQUE NOT NULL,
            hostel TEXT NOT NULL,
            room TEXT NOT NULL,
            department TEXT, course TEXT, year INTEGER, semester INTEGER,
            embedding_file TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        -- recognition_service builds its cache at import time
        CREATE TABLE guests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id TEXT UNIQUE NOT NULL, embedding_file TEXT,
            status TEXT NOT NULL, expires_at DATETIME
        );
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL,
            linked_person_id TEXT
        );
        CREATE TABLE access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_type TEXT NOT NULL, person_identifier TEXT,
            entrance TEXT, decision TEXT
        );
        CREATE TABLE attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_session_id INTEGER NOT NULL, student_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ABSENT'
        );
        CREATE TABLE attendance_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL, class_session_id INTEGER NOT NULL,
            kind TEXT NOT NULL, unit_name TEXT NOT NULL
        );
        CREATE TABLE biometric_consents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL, notice_version TEXT NOT NULL,
            channel TEXT NOT NULL, withdrawn_at DATETIME
        );
        CREATE TABLE watchlist_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL,
            reason TEXT, status TEXT NOT NULL DEFAULT 'ACTIVE',
            embedding_file TEXT, linked_student_id TEXT
        );
        CREATE TABLE data_erasure_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            erasure_reference TEXT UNIQUE NOT NULL, reason TEXT NOT NULL,
            erased_by TEXT NOT NULL, summary TEXT NOT NULL,
            performed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    connection.commit()
    connection.close()


def _seed_student(path, student_id, embeddings_dir, name="Student"):

    connection = sqlite3.connect(path)

    filename = f"{student_id}.npy"
    np.save(os.path.join(embeddings_dir, filename),
            np.array([1.0, 0.0, 0.0], dtype=np.float32))

    connection.execute(
        "INSERT INTO students (student_id, full_name, admission_number, "
        "hostel, room, embedding_file) VALUES (?, ?, ?, 'H', 'R', ?)",
        (student_id, name, "ADM-" + student_id, filename)
    )
    connection.execute(
        "INSERT INTO users (username, role, linked_person_id) "
        "VALUES (?, 'STUDENT', ?)", (student_id.lower() + ".login", student_id)
    )
    for _ in range(3):
        connection.execute(
            "INSERT INTO access_logs (person_type, person_identifier, "
            "entrance, decision) VALUES ('STUDENT', ?, 'Main Gate', 'VERIFIED')",
            (student_id,)
        )
    for session in (1, 2):
        connection.execute(
            "INSERT INTO attendance_records (class_session_id, student_id, "
            "status) VALUES (?, ?, 'PRESENT')", (session, student_id)
        )
        connection.execute(
            "INSERT INTO attendance_notifications (student_id, "
            "class_session_id, kind, unit_name) "
            "VALUES (?, ?, 'ATTENDED', 'Data Structures')", (student_id, session)
        )
    connection.execute(
        "INSERT INTO biometric_consents (student_id, notice_version, channel) "
        "VALUES (?, 'v1', 'SELF')", (student_id,)
    )
    connection.commit()
    connection.close()


def _count(path, query, params=()):

    connection = sqlite3.connect(path)
    n = connection.execute(query, params).fetchone()[0]
    connection.close()
    return n


if __name__ == "__main__":

    print("Testing erasure_service...")

    _install_fake_insightface()

    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_smarthostel.db")
    emb_dir = os.path.join(temp_dir, "embeddings")
    tgt_dir = os.path.join(temp_dir, "targets")
    os.makedirs(emb_dir)
    os.makedirs(tgt_dir)

    _create_schema(db_path)

    import src.db as db
    db.DATABASE_PATH = db_path

    import src.services.recognition_service as recognition_service
    recognition_service.STUDENT_EMBEDDINGS_FOLDER = emb_dir

    from src.services import erasure_service, watchlist_service
    erasure_service.STUDENT_EMBEDDINGS_FOLDER = emb_dir
    watchlist_service.TARGET_EMBEDDINGS_FOLDER = tgt_dir

    _seed_student(db_path, "S-1", emb_dir, "Alice Example")
    _seed_student(db_path, "S-2", emb_dir, "Bob Bystander")

    # ------------------------------------------------------------
    # Dry run: counts, no content, nothing changes
    # ------------------------------------------------------------

    summary = erasure_service.summarize_student_data("S-1")
    assert summary["student_record"] is True
    assert summary["face_template"] is True
    assert summary["login_accounts"] == 1
    assert summary["access_log_entries"] == 3
    assert summary["attendance_records"] == 2
    assert summary["attendance_notifications"] == 2
    assert summary["consent_records"] == 1
    assert "Alice" not in str(summary)
    print("Dry run summary (counts only) ->", summary)
    assert _count(db_path, "SELECT COUNT(*) FROM students") == 2

    try:
        erasure_service.summarize_student_data("NOBODY")
        raise AssertionError("expected NothingToEraseError")
    except erasure_service.NothingToEraseError:
        print("Dry run for an unknown student -> nothing held")

    # ------------------------------------------------------------
    # Guard rails: nothing is touched on a refused erasure
    # ------------------------------------------------------------

    for kwargs, label in [
        (dict(confirm="S-1X", reason="GRADUATED"), "wrong confirm"),
        (dict(confirm="S-1", reason="because"), "unknown reason"),
        (dict(confirm="S-1", reason="Jane Doe asked"), "free-text reason"),
    ]:
        try:
            erasure_service.erase_student("S-1", erased_by="admin1", **kwargs)
            raise AssertionError(f"expected ValueError for {label}")
        except ValueError:
            pass
    assert _count(db_path, "SELECT COUNT(*) FROM students") == 2
    assert _count(db_path, "SELECT COUNT(*) FROM data_erasure_log") == 0
    print("Wrong confirm / unknown reason / free text all refused, nothing changed")

    # ------------------------------------------------------------
    # An ACTIVE watchlist target blocks erasure entirely
    # ------------------------------------------------------------

    connection = sqlite3.connect(db_path)
    np.save(os.path.join(tgt_dir, "TGT-A.npy"), np.array([1.0, 0.0, 0.0]))
    np.save(os.path.join(tgt_dir, "TGT-R.npy"), np.array([1.0, 0.0, 0.0]))
    connection.execute(
        "INSERT INTO watchlist_targets (target_id, full_name, reason, status, "
        "embedding_file, linked_student_id) "
        "VALUES ('TGT-A', 'Alice Example', 'Under investigation', 'ACTIVE', "
        "'TGT-A.npy', 'S-1')"
    )
    connection.commit()
    connection.close()

    try:
        erasure_service.erase_student(
            "S-1", confirm="S-1", reason="SUBJECT_REQUEST", erased_by="admin1"
        )
        raise AssertionError("expected ErasureBlockedError")
    except erasure_service.ErasureBlockedError as error:
        assert error.active_watchlist_targets == ["TGT-A"]
        print("Active watchlist target blocks erasure ->", error)
    assert _count(db_path, "SELECT COUNT(*) FROM students WHERE student_id='S-1'") == 1
    assert os.path.exists(os.path.join(emb_dir, "S-1.npy"))
    assert os.path.exists(os.path.join(tgt_dir, "TGT-A.npy"))

    # Resolved -> erasure proceeds, but the target RECORD is retained.
    connection = sqlite3.connect(db_path)
    connection.execute("UPDATE watchlist_targets SET status='RESOLVED'")
    connection.execute(
        "INSERT INTO watchlist_targets (target_id, full_name, status, "
        "embedding_file, linked_student_id) "
        "VALUES ('TGT-R', 'Alice Example', 'RESOLVED', 'TGT-R.npy', 'S-1')"
    )
    connection.commit()
    connection.close()

    # ------------------------------------------------------------
    # The erasure itself
    # ------------------------------------------------------------

    result = erasure_service.erase_student(
        "S-1", confirm="S-1", reason="GRADUATED", erased_by="admin1"
    )

    assert result["erased"]["access_log_entries"] == 3
    assert result["face_files_removed"] == 3  # student + 2 target copies
    assert result["face_files_failed"] == []
    assert sorted(result["retained_for_review"]["watchlist_target_records"]) == [
        "TGT-A", "TGT-R"]
    print("Erased ->", {k: result[k] for k in ("erasure_reference", "reason",
                                                "face_files_removed")})

    for table, column in [
        ("students", "student_id"),
        ("attendance_records", "student_id"),
        ("attendance_notifications", "student_id"),
        ("biometric_consents", "student_id"),
        ("users", "linked_person_id"),
    ]:
        assert _count(
            db_path, f"SELECT COUNT(*) FROM {table} WHERE {column} = 'S-1'"
        ) == 0, table
    assert _count(
        db_path,
        "SELECT COUNT(*) FROM access_logs WHERE person_identifier = 'S-1'"
    ) == 0
    for folder, name in [(emb_dir, "S-1.npy"), (tgt_dir, "TGT-A.npy"),
                         (tgt_dir, "TGT-R.npy")]:
        assert not os.path.exists(os.path.join(folder, name)), name
    print("Every table and every face file for S-1 is gone")

    # The security target records survive, scrubbed of the face + link.
    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT target_id, full_name, embedding_file, linked_student_id "
        "FROM watchlist_targets ORDER BY target_id"
    ).fetchall()
    connection.close()
    assert rows == [("TGT-A", "Alice Example", None, None),
                    ("TGT-R", "Alice Example", None, None)], rows
    print("Watchlist records retained for review, face + link removed ->", rows)

    # A different student is completely untouched.
    assert _count(db_path, "SELECT COUNT(*) FROM students WHERE student_id='S-2'") == 1
    assert _count(db_path, "SELECT COUNT(*) FROM access_logs WHERE person_identifier='S-2'") == 3
    assert _count(db_path, "SELECT COUNT(*) FROM attendance_records WHERE student_id='S-2'") == 2
    assert os.path.exists(os.path.join(emb_dir, "S-2.npy"))
    print("Another student's data is untouched")

    # The recognition cache no longer holds the erased face.
    assert not any(
        e["student_id"] == "S-1"
        for e in recognition_service.identity_cache.students
    )

    # ------------------------------------------------------------
    # The erasure log proves it happened without identifying anyone
    # ------------------------------------------------------------

    connection = sqlite3.connect(db_path)
    log = connection.execute(
        "SELECT erasure_reference, reason, erased_by, summary "
        "FROM data_erasure_log"
    ).fetchall()
    connection.close()
    assert len(log) == 1
    assert log[0][0] == result["erasure_reference"]
    assert log[0][1:3] == ("GRADUATED", "admin1")
    for needle in ("S-1", "Alice", "ADM-S-1"):
        assert needle not in " ".join(str(v) for v in log[0]), needle
    print("Erasure log holds the reference/reason/admin, no student identity")

    # Re-running finds nothing left (idempotent from the caller's view).
    try:
        erasure_service.erase_student(
            "S-1", confirm="S-1", reason="GRADUATED", erased_by="admin1"
        )
        raise AssertionError("expected NothingToEraseError")
    except erasure_service.NothingToEraseError:
        print("Erasing again -> nothing held")

    # ------------------------------------------------------------
    # Leftover data without a student row is still erased (e.g. after
    # an earlier partial cleanup), rather than reported as "not found".
    # ------------------------------------------------------------

    connection = sqlite3.connect(db_path)
    connection.execute(
        "INSERT INTO attendance_records (class_session_id, student_id) "
        "VALUES (9, 'ORPHAN')"
    )
    connection.commit()
    connection.close()
    orphan = erasure_service.erase_student(
        "ORPHAN", confirm="ORPHAN", reason="OTHER", erased_by="admin1"
    )
    assert orphan["erased"]["student_record"] is False
    assert orphan["erased"]["attendance_records"] == 1
    print("Orphaned rows with no student record are erased too")

    # ------------------------------------------------------------
    # Atomicity: a failure part-way leaves the database untouched
    # ------------------------------------------------------------

    _seed_student(db_path, "S-3", emb_dir, "Carol Atomic")
    connection = sqlite3.connect(db_path)
    connection.execute("DROP TABLE data_erasure_log")  # the LAST statement fails
    connection.commit()
    connection.close()

    try:
        erasure_service.erase_student(
            "S-3", confirm="S-3", reason="GRADUATED", erased_by="admin1"
        )
        raise AssertionError("expected the log insert to fail")
    except sqlite3.OperationalError:
        pass
    assert _count(db_path, "SELECT COUNT(*) FROM students WHERE student_id='S-3'") == 1
    assert _count(db_path, "SELECT COUNT(*) FROM attendance_records WHERE student_id='S-3'") == 2
    assert _count(db_path, "SELECT COUNT(*) FROM access_logs WHERE person_identifier='S-3'") == 3
    assert os.path.exists(os.path.join(emb_dir, "S-3.npy"))
    print("A failure mid-erasure rolled everything back; the face file was kept")

    # A stored filename that tries to escape the folder is never deleted
    # (and is reported, not silently skipped). data_erasure_log was
    # dropped above to force the rollback, so recreate it first.
    outside = os.path.join(temp_dir, "precious.txt")
    open(outside, "w").write("do not delete")
    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE students SET embedding_file = '../precious.txt' "
        "WHERE student_id = 'S-3'"
    )
    connection.execute(
        "CREATE TABLE data_erasure_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "erasure_reference TEXT UNIQUE NOT NULL, reason TEXT NOT NULL, "
        "erased_by TEXT NOT NULL, summary TEXT NOT NULL, "
        "performed_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
    connection.commit()
    connection.close()

    unsafe = erasure_service.erase_student(
        "S-3", confirm="S-3", reason="OTHER", erased_by="admin1"
    )
    assert os.path.exists(outside)
    assert unsafe["face_files_failed"] == ["../precious.txt"]
    assert unsafe["face_files_removed"] == 0
    print("A path-escaping filename is never deleted, and is reported")

    import shutil
    shutil.rmtree(temp_dir)

    print("\nerasure_service smoke test passed.")
