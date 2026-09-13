import os
import sys
import sqlite3
import tempfile
import types

import numpy as np


# ============================================================
# FAKE `insightface` — same approach as test_enrollment_service.py:
# this sandbox has no model weights or GPU/CPU ONNX runtime setup.
# access_service.py's UNKNOWN branch goes through unknown_service,
# which imports recognition_service's `app` at module level.
# ============================================================

_NEXT_FACES = []


class _FakeFace:

    def __init__(self, embedding):
        self.embedding = np.array(embedding, dtype=np.float32)
        self.bbox = np.array([0, 0, 50, 50], dtype=np.float32)


class _FakeFaceAnalysis:

    def __init__(self, name, providers):
        pass

    def prepare(self, ctx_id, det_size):
        pass

    def get(self, image):
        return _NEXT_FACES.pop(0)


def _install_fake_insightface():

    fake_insightface = types.ModuleType("insightface")
    fake_insightface_app = types.ModuleType("insightface.app")
    fake_insightface_app.FaceAnalysis = _FakeFaceAnalysis
    fake_insightface.app = fake_insightface_app

    sys.modules["insightface"] = fake_insightface
    sys.modules["insightface.app"] = fake_insightface_app


def _queue_faces(*face_lists):
    _NEXT_FACES.clear()
    _NEXT_FACES.extend(face_lists)


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


def _access_log_count(db_path, decision=None):

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    if decision:
        cursor.execute(
            "SELECT COUNT(*) FROM access_logs WHERE decision = ?", (decision,)
        )
    else:
        cursor.execute("SELECT COUNT(*) FROM access_logs")

    count = cursor.fetchone()[0]
    connection.close()
    return count


if __name__ == "__main__":

    print("Testing access_service against a faked InsightFace...")

    _install_fake_insightface()

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")
    temp_unknown_images_dir = os.path.join(temp_dir, "unknown_images")
    temp_unknown_embeddings_dir = os.path.join(temp_dir, "unknown_embeddings")
    os.makedirs(temp_unknown_images_dir)
    os.makedirs(temp_unknown_embeddings_dir)

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    import src.services.recognition_service as recognition_service
    import src.services.unknown_service as unknown_service
    unknown_service.UNKNOWN_IMAGES_FOLDER = temp_unknown_images_dir
    unknown_service.UNKNOWN_EMBEDDINGS_FOLDER = temp_unknown_embeddings_dir

    from src.services import access_service

    # should_log has module-level cooldown state shared across the
    # whole test run — use a distinct identifier per scenario so
    # scenarios don't interfere with each other's cooldown timers.

    # ------------------------------------------------------------
    # STUDENT — live face -> GRANTED, logged as VERIFIED
    # ------------------------------------------------------------

    result = access_service.process_access({
        "status": "STUDENT",
        "student_id": "STU-1",
        "full_name": "Alice Example",
        "admission_number": "ADM-1",
        "hostel": "Nyayo",
        "room": "A1",
        "recognition_score": 0.93,
        "liveness_score": 0.85,
        "is_live": True
    })

    assert result["access_status"] == "GRANTED"
    assert result["person_type"] == "STUDENT"
    assert _access_log_count(temp_db_path, "VERIFIED") == 1
    print("Live student match -> GRANTED, logged VERIFIED ->", result)

    # Same identifier immediately again -> within cooldown, not re-logged.
    access_service.process_access({
        "status": "STUDENT",
        "student_id": "STU-1",
        "full_name": "Alice Example",
        "admission_number": "ADM-1",
        "hostel": "Nyayo",
        "room": "A1",
        "recognition_score": 0.93,
        "liveness_score": 0.85,
        "is_live": True
    })
    assert _access_log_count(temp_db_path, "VERIFIED") == 1
    print("Repeat match within cooldown window is not re-logged")

    # ------------------------------------------------------------
    # STUDENT — liveness failed -> REVIEW_REQUIRED, logged LIVENESS_FAILED
    # ------------------------------------------------------------

    spoof_result = access_service.process_access({
        "status": "STUDENT",
        "student_id": "STU-2",
        "full_name": "Bob Example",
        "admission_number": "ADM-2",
        "hostel": "Nyayo",
        "room": "A2",
        "recognition_score": 0.91,
        "liveness_score": 0.15,
        "is_live": False,
        "liveness_reasons": ["low_texture_variance"]
    })

    assert spoof_result["access_status"] == "REVIEW_REQUIRED"
    assert spoof_result["person_type"] == "SUSPECTED_SPOOF"
    assert _access_log_count(temp_db_path, "LIVENESS_FAILED") == 1
    print("Matched student failing liveness -> routed to review ->", spoof_result)

    # ------------------------------------------------------------
    # ADMITTED_GUEST — live -> GRANTED, logged AG_VALID
    # ------------------------------------------------------------

    guest_result = access_service.process_access({
        "status": "ADMITTED_GUEST",
        "guest_id": "AG-1",
        "expires_at": "2026-09-14T00:00:00",
        "recognition_score": 0.88,
        "liveness_score": 0.7,
        "is_live": True
    })

    assert guest_result["access_status"] == "GRANTED"
    assert guest_result["person_type"] == "ADMITTED_GUEST"
    assert _access_log_count(temp_db_path, "AG_VALID") == 1
    print("Live admitted guest -> GRANTED, logged AG_VALID ->", guest_result)

    # ------------------------------------------------------------
    # ADMITTED_GUEST — liveness failed -> REVIEW_REQUIRED
    # ------------------------------------------------------------

    guest_spoof_result = access_service.process_access({
        "status": "ADMITTED_GUEST",
        "guest_id": "AG-2",
        "expires_at": "2026-09-14T00:00:00",
        "recognition_score": 0.80,
        "liveness_score": 0.10,
        "is_live": False
    })

    assert guest_spoof_result["access_status"] == "REVIEW_REQUIRED"
    assert _access_log_count(temp_db_path, "LIVENESS_FAILED") == 2
    print("Admitted guest failing liveness -> routed to review ->", guest_spoof_result)

    # ------------------------------------------------------------
    # UNKNOWN — no image provided
    # ------------------------------------------------------------

    no_image_result = access_service.process_access({"status": "UNKNOWN"})
    assert no_image_result["access_status"] == "REVIEW_REQUIRED"
    assert no_image_result["person_type"] == "UNKNOWN"
    assert "no image was provided" in no_image_result["message"]
    print("Unknown person with no image -> review required, no crash")

    # ------------------------------------------------------------
    # UNKNOWN — with image, new unknown person captured
    # ------------------------------------------------------------

    _queue_faces([_FakeFace([1.0, 0.0, 0.0])])
    blank_image = np.zeros((100, 100, 3), dtype=np.uint8)

    unknown_result = access_service.process_access(
        {"status": "UNKNOWN"}, image=blank_image
    )

    assert unknown_result["access_status"] == "REVIEW_REQUIRED"
    assert unknown_result["unknown_id"].startswith("UNK-")
    assert unknown_result["status"] == "PENDING_REVIEW"
    print("New unknown person captured ->", unknown_result)

    pending_count = sqlite3.connect(temp_db_path).execute(
        "SELECT COUNT(*) FROM unknown_persons"
    ).fetchone()[0]
    assert pending_count == 1
    print("Unknown person actually persisted to unknown_persons")

    # ------------------------------------------------------------
    # NO_FACE
    # ------------------------------------------------------------

    no_face_result = access_service.process_access({"status": "NO_FACE"})
    assert no_face_result == {
        "access_status": "NO_ACTION",
        "person_type": None,
        "message": "No face detected"
    }
    print("NO_FACE -> NO_ACTION, as expected")

    # ------------------------------------------------------------
    # FALLBACK — unrecognized status
    # ------------------------------------------------------------

    fallback_result = access_service.process_access({"status": "SOMETHING_ELSE"})
    assert fallback_result["access_status"] == "ERROR"
    print("Unrecognized status -> ERROR fallback, as expected")

    import shutil
    shutil.rmtree(temp_dir)

    print("\naccess_service smoke test passed.")
