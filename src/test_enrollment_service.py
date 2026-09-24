import os
import sys
import sqlite3
import tempfile
import types

import numpy as np


# ============================================================
# FAKE `insightface` — this sandbox has no model weights or GPU/CPU
# ONNX runtime setup, and downloading them is out of scope for a
# unit test. This stands in for FaceAnalysis so recognition_service
# (and enrollment_service, which imports from it) can be imported
# and exercised without the real model.
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
            department TEXT,
            course TEXT,
            year INTEGER,
            semester INTEGER,
            embedding_file TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Only what enroll_own_face's linked_person_id lookup needs — not
    # the real users table's full schema.
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            linked_person_id TEXT
        )
    """)

    # recognition_service.py builds its IdentityCache at import time,
    # which queries both students and guests — this table just needs
    # to exist, empty, for that import-time query to succeed.
    connection.execute("""
        CREATE TABLE IF NOT EXISTS guests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id TEXT UNIQUE NOT NULL,
            embedding_file TEXT,
            status TEXT NOT NULL,
            expires_at DATETIME
        )
    """)

    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing enrollment_service against a faked InsightFace...")

    _install_fake_insightface()

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")
    temp_embeddings_dir = os.path.join(temp_dir, "embeddings")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    import src.services.recognition_service as recognition_service
    recognition_service.STUDENT_EMBEDDINGS_FOLDER = temp_embeddings_dir

    from src.services import enrollment_service
    enrollment_service.STUDENT_EMBEDDINGS_FOLDER = temp_embeddings_dir
    os.makedirs(temp_embeddings_dir, exist_ok=True)

    blank_image = np.zeros((100, 100, 3), dtype=np.uint8)

    # ------------------------------------------------------------
    # ONE IMAGE, ONE FACE -> SUCCESS
    # ------------------------------------------------------------

    _queue_faces([_FakeFace([1.0, 0.0, 0.0])])

    result = enrollment_service.enroll_student_face(
        student_id="STU-100",
        full_name="Alice Example",
        admission_number="ADM-100",
        hostel="Nyayo",
        room="A1",
        images=[blank_image]
    )

    assert result["samples_used"] == 1
    assert result["samples_skipped"] == 0
    assert os.path.exists(
        os.path.join(temp_embeddings_dir, "STU-100.npy")
    )
    print("Single-image enrollment ->", result)

    # ------------------------------------------------------------
    # THREE IMAGES: no-face, multi-face, one good face -> averaged
    # from the single good sample, two skipped
    # ------------------------------------------------------------

    _queue_faces(
        [],
        [_FakeFace([1.0, 0.0, 0.0]), _FakeFace([0.0, 1.0, 0.0])],
        [_FakeFace([0.0, 0.0, 1.0])]
    )

    result = enrollment_service.enroll_student_face(
        student_id="STU-101",
        full_name="Bob Example",
        admission_number="ADM-101",
        hostel="Nyayo",
        room="A2",
        images=[blank_image, blank_image, blank_image]
    )

    assert result["samples_used"] == 1
    assert result["samples_skipped"] == 2
    print("Mixed-quality enrollment ->", result)

    # ------------------------------------------------------------
    # DUPLICATE student_id -> rejected, embedding file cleaned up
    # ------------------------------------------------------------

    _queue_faces([_FakeFace([1.0, 0.0, 0.0])])

    try:
        enrollment_service.enroll_student_face(
            student_id="STU-100",
            full_name="Alice Duplicate",
            admission_number="ADM-999",
            hostel="Nyayo",
            room="A9",
            images=[blank_image]
        )
        raise AssertionError("Expected ValueError for duplicate student_id")
    except ValueError as error:
        print("Duplicate student_id rejected as expected:", error)

    # ------------------------------------------------------------
    # NO IMAGES -> rejected immediately
    # ------------------------------------------------------------

    try:
        enrollment_service.enroll_student_face(
            student_id="STU-102",
            full_name="No Photos",
            admission_number="ADM-102",
            hostel="Nyayo",
            room="A3",
            images=[]
        )
        raise AssertionError("Expected ValueError for no images")
    except ValueError as error:
        print("Empty image list rejected as expected:", error)

    # ------------------------------------------------------------
    # department/course/year/semester (Dean of School scoping +
    # SmartAttendance schedule matching, docs/PRD.md §8) -> optional,
    # stored when supplied
    # ------------------------------------------------------------

    _queue_faces([_FakeFace([0.5, 0.5, 0.0])])

    classified_result = enrollment_service.enroll_student_face(
        student_id="STU-103",
        full_name="Carol Classified",
        admission_number="ADM-103",
        hostel="Nyayo",
        room="A4",
        images=[blank_image],
        department="School of Computing",
        course="BSc Computer Science",
        year=2,
        semester=1
    )

    assert classified_result["department"] == "School of Computing"
    assert classified_result["course"] == "BSc Computer Science"
    assert classified_result["year"] == 2
    assert classified_result["semester"] == 1
    print("department/course/year/semester stored when supplied ->", classified_result)

    # ------------------------------------------------------------
    # create_student_record: a bare record, no embedding yet
    # ------------------------------------------------------------

    bare = enrollment_service.create_student_record(
        student_id="STU-200",
        full_name="Dan Bare",
        admission_number="ADM-200",
        hostel="Nyayo",
        room="B1"
    )

    assert bare["face_enrolled"] is False

    connection = sqlite3.connect(temp_db_path)
    row = connection.execute(
        "SELECT embedding_file FROM students WHERE student_id = ?",
        ("STU-200",)
    ).fetchone()
    connection.close()
    assert row[0] is None
    print("create_student_record leaves embedding_file NULL ->", bare)

    try:
        enrollment_service.create_student_record(
            student_id="STU-200",
            full_name="Dan Duplicate",
            admission_number="ADM-201",
            hostel="Nyayo",
            room="B2"
        )
        raise AssertionError("Expected ValueError for duplicate student_id")
    except ValueError as error:
        print("create_student_record rejects duplicate student_id:", error)

    # ------------------------------------------------------------
    # enroll_own_face: liveness check is always run — stub it so this
    # test controls pass/fail deterministically rather than depending
    # on real liveness_service heuristics against a fake blank image.
    # ------------------------------------------------------------

    def _link_user(username, student_id):
        connection = sqlite3.connect(temp_db_path)
        connection.execute(
            "INSERT INTO users (username, linked_person_id) VALUES (?, ?)",
            (username, student_id)
        )
        connection.commit()
        connection.close()

    _link_user("dan.bare", "STU-200")

    enrollment_service.check_liveness = (
        lambda image, face: {
            "is_live": True,
            "liveness_score": 0.9,
            "reasons": []
        }
    )

    _queue_faces([_FakeFace([0.2, 0.3, 0.4])])

    self_result = enrollment_service.enroll_own_face(
        "dan.bare",
        [blank_image]
    )

    assert self_result["student_id"] == "STU-200"
    assert self_result["samples_used"] == 1
    assert os.path.exists(
        os.path.join(temp_embeddings_dir, "STU-200.npy")
    )
    print("enroll_own_face (liveness passes) ->", self_result)

    # No linked profile at all -> rejected
    try:
        enrollment_service.enroll_own_face("no.such.user", [blank_image])
        raise AssertionError("Expected ValueError for no linked profile")
    except ValueError as error:
        print("enroll_own_face rejects an unlinked account:", error)

    # Linked, but the student record doesn't exist yet -> rejected
    _link_user("ghost.student", "STU-DOES-NOT-EXIST")
    try:
        enrollment_service.enroll_own_face("ghost.student", [blank_image])
        raise AssertionError("Expected ValueError for missing student record")
    except ValueError as error:
        print("enroll_own_face rejects a not-yet-registered student:", error)

    # Liveness fails on every photo -> rejected, nothing written
    enrollment_service.check_liveness = (
        lambda image, face: {
            "is_live": False,
            "liveness_score": 0.1,
            "reasons": ["texture_out_of_expected_range"]
        }
    )
    _queue_faces([_FakeFace([0.1, 0.1, 0.1])])
    try:
        enrollment_service.enroll_own_face("dan.bare", [blank_image])
        raise AssertionError("Expected ValueError for failed liveness check")
    except ValueError as error:
        print("enroll_own_face rejects a failed liveness check:", error)

    import shutil
    shutil.rmtree(temp_dir)

    print("\nenrollment_service smoke test passed.")
