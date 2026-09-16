import os
import sqlite3
import sys
import tempfile
import types

import numpy as np


def _install_fake_insightface():

    fake_insightface = types.ModuleType("insightface")
    fake_insightface_app = types.ModuleType("insightface.app")

    class _FakeFaceAnalysis:

        def __init__(self, name, providers):
            pass

        def prepare(self, ctx_id, det_size):
            pass

        def get(self, image):
            return _NEXT_FACES.pop(0)

    fake_insightface_app.FaceAnalysis = _FakeFaceAnalysis
    fake_insightface.app = fake_insightface_app

    sys.modules["insightface"] = fake_insightface
    sys.modules["insightface.app"] = fake_insightface_app


_NEXT_FACES = []


def _queue_faces(*face_lists):
    _NEXT_FACES.clear()
    _NEXT_FACES.extend(face_lists)


class FakeFace:

    def __init__(self, embedding):
        self.embedding = np.array(embedding, dtype=np.float32)


def _create_schema(path):

    connection = sqlite3.connect(path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            admission_number TEXT UNIQUE NOT NULL,
            hostel TEXT NOT NULL,
            room TEXT NOT NULL,
            embedding_file TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS guests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id TEXT UNIQUE NOT NULL,
            embedding_file TEXT,
            status TEXT NOT NULL,
            expires_at DATETIME
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            description TEXT,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            embedding_file TEXT,
            linked_student_id TEXT,
            created_by TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_by TEXT,
            resolved_at DATETIME
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
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing watchlist_service against a faked InsightFace...")

    _install_fake_insightface()

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")
    temp_embeddings_dir = os.path.join(temp_dir, "watchlist_embeddings")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    from src.services import watchlist_service
    watchlist_service.TARGET_EMBEDDINGS_FOLDER = temp_embeddings_dir
    os.makedirs(temp_embeddings_dir, exist_ok=True)

    temp_student_embeddings_dir = os.path.join(temp_dir, "student_embeddings")
    watchlist_service.STUDENT_EMBEDDINGS_FOLDER = temp_student_embeddings_dir
    os.makedirs(temp_student_embeddings_dir, exist_ok=True)

    blank_image = np.zeros((100, 100, 3), dtype=np.uint8)

    # ------------------------------------------------------------
    # CREATE — with a reference photo -> stores an embedding
    # ------------------------------------------------------------

    _queue_faces([FakeFace([1.0, 0.0, 0.0])])

    target = watchlist_service.create_target(
        full_name="Person Of Interest",
        description="Tall, red jacket",
        reason="Reported theft",
        images=[blank_image],
        created_by="security1"
    )

    assert target["target_id"].startswith("TGT-")
    assert target["status"] == "ACTIVE"
    assert target["embedding_file"] is not None
    assert os.path.exists(
        os.path.join(temp_embeddings_dir, target["embedding_file"])
    )
    print("Created target with a reference photo ->", target)

    # ------------------------------------------------------------
    # CREATE — no photo -> record exists, but no embedding (not
    # matchable by the live pipeline until one is added)
    # ------------------------------------------------------------

    no_photo_target = watchlist_service.create_target(
        full_name="Named Only",
        created_by="security1"
    )

    assert no_photo_target["embedding_file"] is None
    print("Created target with no photo -> no embedding yet ->", no_photo_target)

    # ------------------------------------------------------------
    # CREATE — a photo with no usable face -> rejected
    # ------------------------------------------------------------

    _queue_faces([])

    try:
        watchlist_service.create_target(
            full_name="Bad Photo",
            images=[blank_image]
        )
        raise AssertionError("Expected ValueError for no usable face")
    except ValueError as error:
        print("No usable face in the photo raised, as expected:", error)

    # ------------------------------------------------------------
    # CREATE — neither full_name nor admission_number -> rejected
    # ------------------------------------------------------------

    try:
        watchlist_service.create_target()
        raise AssertionError("Expected ValueError with no identity supplied")
    except ValueError as error:
        print("No full_name/admission_number raised, as expected:", error)

    # ------------------------------------------------------------
    # CREATE — by admission_number: reuses an enrolled student's own
    # embedding and derives full_name from their record, ignoring any
    # full_name explicitly supplied alongside it
    # ------------------------------------------------------------

    student_embedding = np.array([0.6, 0.8, 0.0], dtype=np.float32)
    np.save(
        os.path.join(temp_student_embeddings_dir, "STU-1.npy"),
        student_embedding
    )

    connection = sqlite3.connect(temp_db_path)
    connection.execute("""
        INSERT INTO students (
            student_id, full_name, admission_number,
            hostel, room, embedding_file
        )
        VALUES ('STU-1', 'Alice Wanjiru', 'ADM-100', 'Nyayo', 'A1', 'STU-1.npy')
    """)
    connection.commit()
    connection.close()

    linked_target = watchlist_service.create_target(
        full_name="This name should be overridden",
        reason="Under investigation",
        admission_number="ADM-100",
        created_by="security1"
    )

    assert linked_target["full_name"] == "Alice Wanjiru"
    assert linked_target["linked_student_id"] == "STU-1"
    assert linked_target["embedding_file"] is not None

    copied_embedding = np.load(
        os.path.join(temp_embeddings_dir, linked_target["embedding_file"])
    )
    assert np.allclose(copied_embedding, student_embedding)
    print("Created target from an enrolled student's admission_number ->", linked_target)

    try:
        watchlist_service.create_target(admission_number="ADM-NOPE")
        raise AssertionError("Expected ValueError for an unknown admission_number")
    except ValueError as error:
        print("Unknown admission_number raised, as expected:", error)

    # ------------------------------------------------------------
    # LIST / FILTER
    # ------------------------------------------------------------

    all_targets = watchlist_service.list_targets()
    assert len(all_targets) == 3
    print(f"All targets: {len(all_targets)}")

    active_targets = watchlist_service.list_targets(status="active")
    assert len(active_targets) == 3
    print(f"Active targets: {len(active_targets)}")

    # ------------------------------------------------------------
    # RESOLVE / REACTIVATE
    # ------------------------------------------------------------

    resolved = watchlist_service.resolve_target(
        target["target_id"], "security1"
    )
    assert resolved is True

    refreshed = watchlist_service.get_target(target["target_id"])
    assert refreshed["status"] == "RESOLVED"
    assert refreshed["resolved_by"] == "security1"
    print("Target resolved ->", refreshed)

    assert len(watchlist_service.list_targets(status="active")) == 2
    print("Resolved target excluded from the active filter")

    missing_resolve = watchlist_service.resolve_target("TGT-NOPE", "x")
    assert missing_resolve is False
    print("Resolving a non-existent target returns False, as expected")

    reactivated = watchlist_service.reactivate_target(target["target_id"])
    assert reactivated is True

    reactivated_target = watchlist_service.get_target(target["target_id"])
    assert reactivated_target["status"] == "ACTIVE"
    assert reactivated_target["resolved_by"] is None
    print("Target reactivated, resolved_by cleared ->", reactivated_target)

    # ------------------------------------------------------------
    # SIGHTINGS — the actual "tracking" history
    # ------------------------------------------------------------

    connection = sqlite3.connect(temp_db_path)
    connection.execute("""
        INSERT INTO access_logs (person_type, person_identifier, entrance, decision)
        VALUES ('TARGET', ?, 'Main Gate', 'TARGET_ALERT')
    """, (target["target_id"],))
    connection.execute("""
        INSERT INTO access_logs (person_type, person_identifier, entrance, decision)
        VALUES ('TARGET', ?, 'Side Gate', 'TARGET_ALERT')
    """, (target["target_id"],))
    connection.execute("""
        INSERT INTO access_logs (person_type, person_identifier, entrance, decision)
        VALUES ('TARGET', ?, 'Main Gate', 'TARGET_ALERT')
    """, (target["target_id"],))
    connection.execute("""
        INSERT INTO access_logs (person_type, person_identifier, entrance, decision)
        VALUES ('STUDENT', 'STU-1', 'Main Gate', 'VERIFIED')
    """)
    connection.commit()
    connection.close()

    sightings = watchlist_service.get_sightings(target["target_id"])
    assert len(sightings) == 3
    assert {row["entrance"] for row in sightings} == {"Main Gate", "Side Gate"}
    print(f"Target sightings (own only, not other people's logs): {len(sightings)} ->", sightings)

    no_sightings = watchlist_service.get_sightings(no_photo_target["target_id"])
    assert no_sightings == []
    print("A target never sighted has an empty sightings list, as expected")

    # ------------------------------------------------------------
    # SIGHTING FREQUENCY — where a target is seen most
    # ------------------------------------------------------------

    frequency = watchlist_service.get_sighting_frequency(target["target_id"])
    assert frequency == [
        {"entrance": "Main Gate", "count": 2},
        {"entrance": "Side Gate", "count": 1}
    ]
    print("Sighting frequency, highest first ->", frequency)

    no_frequency = watchlist_service.get_sighting_frequency(
        no_photo_target["target_id"]
    )
    assert no_frequency == []
    print("A target never sighted has an empty frequency list, as expected")

    import shutil
    shutil.rmtree(temp_dir)

    print("\nwatchlist_service smoke test passed.")
