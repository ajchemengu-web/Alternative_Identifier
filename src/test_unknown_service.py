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

    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing unknown_service against a faked InsightFace...")

    _install_fake_insightface()

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")
    temp_images_dir = os.path.join(temp_dir, "unknown_images")
    temp_embeddings_dir = os.path.join(temp_dir, "unknown_embeddings")
    os.makedirs(temp_images_dir)
    os.makedirs(temp_embeddings_dir)

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    from src.services import unknown_service as us
    us.UNKNOWN_IMAGES_FOLDER = temp_images_dir
    us.UNKNOWN_EMBEDDINGS_FOLDER = temp_embeddings_dir

    blank_image = np.zeros((100, 100, 3), dtype=np.uint8)

    # ------------------------------------------------------------
    # find_duplicate_unknown — pure function
    # ------------------------------------------------------------

    existing = [
        {"unknown_id": "UNK-A", "embedding": np.array([1.0, 0.0, 0.0], dtype=np.float32)},
        {"unknown_id": "UNK-B", "embedding": np.array([0.0, 1.0, 0.0], dtype=np.float32)},
    ]

    duplicate, score = us.find_duplicate_unknown(
        np.array([1.0, 0.0, 0.0], dtype=np.float32), existing
    )
    assert duplicate["unknown_id"] == "UNK-A"
    assert score > us.UNKNOWN_MATCH_THRESHOLD
    print(f"Clear duplicate match -> {duplicate['unknown_id']} ({score:.3f})")

    no_duplicate, score = us.find_duplicate_unknown(
        np.array([0.0, 0.0, 1.0], dtype=np.float32), existing
    )
    assert no_duplicate is None
    print(f"Orthogonal embedding -> no duplicate (score={score:.3f})")

    no_duplicate, score = us.find_duplicate_unknown(
        np.array([1.0, 0.0, 0.0], dtype=np.float32), []
    )
    assert no_duplicate is None and score == -1
    print("No existing unknowns -> no duplicate, as expected")

    # ------------------------------------------------------------
    # create_unknown_person — brand-new person
    # ------------------------------------------------------------

    _queue_faces([FakeFace([1.0, 0.0, 0.0])])

    first = us.create_unknown_person(blank_image)
    assert first["duplicate"] is False
    assert first["status"] == "PENDING_REVIEW"
    assert first["unknown_id"].startswith("UNK-")
    assert os.path.exists(first["image_path"])
    assert os.path.exists(
        os.path.join(temp_embeddings_dir, f"{first['unknown_id']}.npy")
    )
    print("New unknown person created ->", first)

    connection = sqlite3.connect(temp_db_path)
    count = connection.execute(
        "SELECT COUNT(*) FROM unknown_persons"
    ).fetchone()[0]
    connection.close()
    assert count == 1
    print("Exactly one unknown_persons row created")

    # ------------------------------------------------------------
    # create_unknown_person — same face again -> duplicate, no new row
    # ------------------------------------------------------------

    _queue_faces([FakeFace([1.0, 0.0, 0.0])])

    second = us.create_unknown_person(blank_image)
    assert second["duplicate"] is True
    assert second["unknown_id"] == first["unknown_id"]
    print("Same face recaptured -> flagged as duplicate of the first ->", second)

    connection = sqlite3.connect(temp_db_path)
    count = connection.execute(
        "SELECT COUNT(*) FROM unknown_persons"
    ).fetchone()[0]
    connection.close()
    assert count == 1
    print("No new row created for the duplicate capture")

    # ------------------------------------------------------------
    # create_unknown_person — a genuinely different face
    # ------------------------------------------------------------

    _queue_faces([FakeFace([0.0, 1.0, 0.0])])

    third = us.create_unknown_person(blank_image)
    assert third["duplicate"] is False
    assert third["unknown_id"] != first["unknown_id"]
    print("A different face is captured as a new unknown person ->", third)

    # ------------------------------------------------------------
    # create_unknown_person — no face detected
    # ------------------------------------------------------------

    _queue_faces([])

    try:
        us.create_unknown_person(blank_image)
        raise AssertionError("Expected an exception for no detected face")
    except Exception as error:
        assert "No face detected" in str(error)
        print("No detected face raises, as expected:", error)

    # ------------------------------------------------------------
    # load_unknown_embeddings — only PENDING_REVIEW rows load
    # ------------------------------------------------------------

    connection = sqlite3.connect(temp_db_path)
    connection.execute(
        "UPDATE unknown_persons SET status = 'ADMITTED' WHERE unknown_id = ?",
        (first["unknown_id"],),
    )
    connection.commit()
    connection.close()

    remaining = us.load_unknown_embeddings()
    remaining_ids = {u["unknown_id"] for u in remaining}
    assert first["unknown_id"] not in remaining_ids
    assert third["unknown_id"] in remaining_ids
    print("load_unknown_embeddings excludes a reviewed (ADMITTED) row ->", remaining_ids)

    import shutil
    shutil.rmtree(temp_dir)

    print("\nunknown_service smoke test passed.")
