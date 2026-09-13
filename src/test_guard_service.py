import os
import sqlite3
import tempfile
from datetime import datetime, timedelta


def _create_schema(path):

    connection = sqlite3.connect(path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS unknown_persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unknown_id TEXT UNIQUE NOT NULL,
            image_path TEXT NOT NULL,
            embedding_file TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
            detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            reviewed_at DATETIME,
            reviewed_by TEXT
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS guests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id TEXT UNIQUE NOT NULL,
            photo_path TEXT,
            embedding_file TEXT,
            status TEXT NOT NULL,
            admitted_by TEXT,
            admitted_at DATETIME,
            expires_at DATETIME,
            rejected_by TEXT,
            rejected_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


def _insert_unknown(
    connection, unknown_id, image_path, embedding_file,
    status="PENDING_REVIEW", detected_at=None
):

    connection.execute("""
        INSERT INTO unknown_persons (
            unknown_id, image_path, embedding_file, status, detected_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        unknown_id, image_path, embedding_file, status,
        (detected_at or datetime.now()).isoformat()
    ))


if __name__ == "__main__":

    print("Testing guard_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    unknown_embeddings_dir = os.path.join(temp_dir, "unknown_embeddings")
    guest_embeddings_dir = os.path.join(temp_dir, "guest_embeddings")
    os.makedirs(unknown_embeddings_dir)
    os.makedirs(guest_embeddings_dir)

    from src.services import guard_service, retention_service

    guard_service.UNKNOWN_EMBEDDINGS_FOLDER = unknown_embeddings_dir
    guard_service.GUEST_EMBEDDINGS_FOLDER = guest_embeddings_dir
    retention_service.UNKNOWN_EMBEDDINGS_FOLDER = unknown_embeddings_dir
    retention_service.GUEST_EMBEDDINGS_FOLDER = guest_embeddings_dir

    # ------------------------------------------------------------
    # GET PENDING UNKNOWNS
    # ------------------------------------------------------------

    assert guard_service.get_pending_unknowns() == []
    print("No pending unknowns yet -> empty list, as expected")

    now = datetime.now()

    unk1_image = os.path.join(temp_dir, "UNK-1.jpg")
    unk1_embedding = os.path.join(unknown_embeddings_dir, "UNK-1.npy")
    with open(unk1_image, "w") as f:
        f.write("fake image")
    with open(unk1_embedding, "w") as f:
        f.write("fake embedding")

    unk2_image = os.path.join(temp_dir, "UNK-2.jpg")
    unk2_embedding = os.path.join(unknown_embeddings_dir, "UNK-2.npy")
    with open(unk2_image, "w") as f:
        f.write("fake image 2")
    with open(unk2_embedding, "w") as f:
        f.write("fake embedding 2")

    already_reviewed_image = os.path.join(temp_dir, "UNK-3.jpg")
    with open(already_reviewed_image, "w") as f:
        f.write("fake image 3")

    connection = sqlite3.connect(temp_db_path)
    _insert_unknown(
        connection, "UNK-1", unk1_image, "UNK-1.npy",
        detected_at=now - timedelta(minutes=5)
    )
    _insert_unknown(
        connection, "UNK-2", unk2_image, "UNK-2.npy",
        detected_at=now
    )
    _insert_unknown(
        connection, "UNK-3", already_reviewed_image, None,
        status="ADMITTED"
    )
    connection.commit()
    connection.close()

    pending = guard_service.get_pending_unknowns()
    assert len(pending) == 2
    assert pending[0]["unknown_id"] == "UNK-2"  # most recently detected first
    assert pending[1]["unknown_id"] == "UNK-1"
    print(f"Pending unknowns (already-reviewed excluded): {len(pending)}")

    # ------------------------------------------------------------
    # REJECT — not found
    # ------------------------------------------------------------

    missing_reject = guard_service.reject_unknown_person("UNK-MISSING")
    assert missing_reject == {
        "success": False,
        "message": "Unknown person not found"
    }
    print("Rejecting a non-existent unknown_id fails cleanly, as expected")

    # ------------------------------------------------------------
    # REJECT — success, and files are actually purged
    # (this is the retention_service integration added when
    # reject_unknown_person was wired to purge immediately)
    # ------------------------------------------------------------

    assert os.path.exists(unk1_image)
    assert os.path.exists(unk1_embedding)

    reject_result = guard_service.reject_unknown_person(
        "UNK-1", reviewed_by="guard1"
    )
    assert reject_result["success"] is True
    assert reject_result["status"] == "REJECTED"

    assert not os.path.exists(unk1_image)
    assert not os.path.exists(unk1_embedding)
    print("Rejected person's files deleted immediately ->", reject_result)

    connection = sqlite3.connect(temp_db_path)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute(
        "SELECT status, reviewed_by FROM unknown_persons WHERE unknown_id = 'UNK-1'"
    )
    row = cursor.fetchone()
    connection.close()
    assert row["status"] == "REJECTED"
    assert row["reviewed_by"] == "guard1"
    print("Rejected row updated with status + reviewed_by, as expected")

    # Rejecting again is a safe no-op on the (already-gone) files.
    second_reject = guard_service.reject_unknown_person("UNK-1")
    assert second_reject["success"] is True
    print("Re-rejecting an already-rejected person doesn't error")

    # ------------------------------------------------------------
    # ADMIT — already reviewed
    # ------------------------------------------------------------

    already_reviewed_result = guard_service.admit_unknown_person("UNK-3")
    assert already_reviewed_result["success"] is False
    assert "already been reviewed" in already_reviewed_result["message"]
    print("Admitting an already-reviewed person fails cleanly ->", already_reviewed_result)

    # ------------------------------------------------------------
    # ADMIT — not found
    # ------------------------------------------------------------

    missing_admit = guard_service.admit_unknown_person("UNK-MISSING")
    assert missing_admit == {
        "success": False,
        "message": "Unknown person not found"
    }
    print("Admitting a non-existent unknown_id fails cleanly, as expected")

    # ------------------------------------------------------------
    # ADMIT — success
    # ------------------------------------------------------------

    admit_result = guard_service.admit_unknown_person(
        "UNK-2", reviewed_by="guard1"
    )
    assert admit_result["success"] is True
    assert admit_result["guest_id"] == "AG-2"
    assert admit_result["status"] == "AG"
    print("Admitted unknown person ->", admit_result)

    guest_embedding_path = os.path.join(guest_embeddings_dir, "AG-2.npy")
    assert os.path.exists(guest_embedding_path)
    # The original unknown-person embedding is untouched by admit
    # (only reject purges it) — admit copies it to guest storage.
    assert os.path.exists(unk2_embedding)
    print("Embedding copied to guest storage; original left in place")

    connection = sqlite3.connect(temp_db_path)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM guests WHERE guest_id = 'AG-2'")
    guest_row = cursor.fetchone()
    cursor.execute(
        "SELECT status, reviewed_by FROM unknown_persons WHERE unknown_id = 'UNK-2'"
    )
    unknown_row = cursor.fetchone()
    connection.close()

    assert guest_row["status"] == "AG"
    assert guest_row["expires_at"] is not None
    expires_at = datetime.fromisoformat(guest_row["expires_at"])
    assert timedelta(hours=23, minutes=55) < (expires_at - now) < timedelta(hours=24, minutes=5)
    assert unknown_row["status"] == "ADMITTED"
    assert unknown_row["reviewed_by"] == "guard1"
    print("Guest row created with ~24h expiry; unknown row marked ADMITTED")

    # Admitting the same unknown_id again now fails (already reviewed).
    re_admit = guard_service.admit_unknown_person("UNK-2")
    assert re_admit["success"] is False
    print("Re-admitting an already-admitted person fails cleanly")

    # ------------------------------------------------------------
    # ADMIT — missing embedding file on disk
    # ------------------------------------------------------------

    connection = sqlite3.connect(temp_db_path)
    _insert_unknown(
        connection, "UNK-4", os.path.join(temp_dir, "UNK-4.jpg"),
        "UNK-4-does-not-exist.npy"
    )
    connection.commit()
    connection.close()

    missing_embedding_result = guard_service.admit_unknown_person("UNK-4")
    assert missing_embedding_result["success"] is False
    assert "embedding not found" in missing_embedding_result["message"]
    print(
        "Admitting a person whose embedding file is missing from disk "
        "fails cleanly ->", missing_embedding_result
    )

    import shutil
    shutil.rmtree(temp_dir)

    print("\nguard_service smoke test passed.")
