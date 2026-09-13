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


if __name__ == "__main__":

    print("Testing retention_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    from src.services import retention_service

    unknown_embeddings_dir = os.path.join(temp_dir, "unknown_embeddings")
    guest_embeddings_dir = os.path.join(temp_dir, "guest_embeddings")
    os.makedirs(unknown_embeddings_dir)
    os.makedirs(guest_embeddings_dir)
    retention_service.UNKNOWN_EMBEDDINGS_FOLDER = unknown_embeddings_dir
    retention_service.GUEST_EMBEDDINGS_FOLDER = guest_embeddings_dir

    # ------------------------------------------------------------
    # REJECTED PERSON -> IMMEDIATE DELETION
    # ------------------------------------------------------------

    rejected_image_path = os.path.join(temp_dir, "UNK-1.jpg")
    rejected_embedding_path = os.path.join(unknown_embeddings_dir, "UNK-1.npy")

    with open(rejected_image_path, "w") as f:
        f.write("fake image bytes")
    with open(rejected_embedding_path, "w") as f:
        f.write("fake embedding bytes")

    connection = sqlite3.connect(temp_db_path)
    connection.execute("""
        INSERT INTO unknown_persons (unknown_id, image_path, embedding_file, status)
        VALUES ('UNK-1', ?, 'UNK-1.npy', 'REJECTED')
    """, (rejected_image_path,))
    connection.commit()
    connection.close()

    assert os.path.exists(rejected_image_path)
    assert os.path.exists(rejected_embedding_path)

    purged = retention_service.purge_rejected_person("UNK-1")
    assert purged is True
    assert not os.path.exists(rejected_image_path)
    assert not os.path.exists(rejected_embedding_path)
    print("Rejected person's image + embedding files deleted, as expected")

    missing_purge = retention_service.purge_rejected_person("UNK-DOES-NOT-EXIST")
    assert missing_purge is False
    print("Purging a non-existent unknown_id returns False, as expected")

    # Purging twice (files already gone) doesn't raise.
    retention_service.purge_rejected_person("UNK-1")
    print("Purging an already-purged person is a safe no-op")

    # ------------------------------------------------------------
    # EXPIRED GUESTS -> AUTOMATIC 24-HOUR DELETION
    # ------------------------------------------------------------

    now = datetime.now()

    expired_photo = os.path.join(temp_dir, "AG-1.jpg")
    expired_embedding = os.path.join(guest_embeddings_dir, "AG-1.npy")
    still_active_embedding = os.path.join(guest_embeddings_dir, "AG-2.npy")

    with open(expired_photo, "w") as f:
        f.write("fake photo")
    with open(expired_embedding, "w") as f:
        f.write("fake embedding")
    with open(still_active_embedding, "w") as f:
        f.write("fake embedding")

    connection = sqlite3.connect(temp_db_path)
    connection.execute("""
        INSERT INTO guests (guest_id, photo_path, embedding_file, status, admitted_at, expires_at)
        VALUES ('AG-1', ?, 'AG-1.npy', 'AG', ?, ?)
    """, (
        expired_photo,
        (now - timedelta(hours=25)).isoformat(),
        (now - timedelta(hours=1)).isoformat(),
    ))
    connection.execute("""
        INSERT INTO guests (guest_id, photo_path, embedding_file, status, admitted_at, expires_at)
        VALUES ('AG-2', NULL, 'AG-2.npy', 'AG', ?, ?)
    """, (
        now.isoformat(),
        (now + timedelta(hours=23)).isoformat(),
    ))
    connection.execute("""
        INSERT INTO guests (guest_id, photo_path, embedding_file, status, admitted_at, expires_at)
        VALUES ('AG-3', NULL, NULL, 'REJECTED', NULL, NULL)
    """)
    connection.commit()
    connection.close()

    purged_ids = retention_service.purge_expired_guests(now=now)
    assert purged_ids == ["AG-1"]
    assert not os.path.exists(expired_photo)
    assert not os.path.exists(expired_embedding)
    assert os.path.exists(still_active_embedding)
    print("Expired admitted guest purged; still-active guest untouched ->", purged_ids)

    connection = sqlite3.connect(temp_db_path)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute("SELECT status, photo_path, embedding_file FROM guests WHERE guest_id = 'AG-1'")
    row = cursor.fetchone()
    connection.close()

    assert row["status"] == "EXPIRED"
    assert row["photo_path"] is None
    assert row["embedding_file"] is None
    print("Expired guest's row updated to EXPIRED with files nulled out ->", dict(row))

    # Running the sweep again is a no-op (AG-1 no longer status='AG').
    second_sweep = retention_service.purge_expired_guests(now=now)
    assert second_sweep == []
    print("Re-running the sweep finds nothing left to purge, as expected")

    import shutil
    shutil.rmtree(temp_dir)

    print("\nretention_service smoke test passed.")
