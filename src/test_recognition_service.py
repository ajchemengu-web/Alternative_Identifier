import os
import sqlite3
import sys
import tempfile
import types

import numpy as np


def _create_schema(path):

    connection = sqlite3.connect(path)

    # recognition_service.py's IdentityCache queries both tables at
    # import time (module-level `identity_cache = IdentityCache()`)
    # — they just need to exist, empty, for that to succeed. The
    # actual test data below is injected directly into the cache
    # instance instead of round-tripping through these tables.
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

    connection.commit()
    connection.close()


# ============================================================
# FAKE `insightface` — recognition_service.py loads the real
# FaceAnalysis model at import time; this sandbox has no model
# weights/ONNX runtime set up for it, same as test_enrollment_
# service.py and test_access_service.py.
# ============================================================

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

    def __init__(self, embedding, bbox=(220, 140, 420, 380)):

        self.embedding = np.array(embedding, dtype=np.float32)
        self.bbox = np.array(bbox, dtype=np.float32)


if __name__ == "__main__":

    print("Testing recognition_service against a faked InsightFace...")

    _install_fake_insightface()

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")
    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    from src.services import recognition_service as rs

    # ------------------------------------------------------------
    # find_best_match — pure function, no cache/DB involved
    # ------------------------------------------------------------

    identities = [
        {"label": "A", "embedding": np.array([1.0, 0.0, 0.0], dtype=np.float32)},
        {"label": "B", "embedding": np.array([0.0, 1.0, 0.0], dtype=np.float32)},
    ]

    match, score = rs.find_best_match(
        np.array([1.0, 0.0, 0.0], dtype=np.float32), identities
    )
    assert match["label"] == "A"
    assert score > 0.99
    print(f"Clear match -> label={match['label']} score={score:.3f}")

    match, score = rs.find_best_match(
        np.array([0.0, 0.0, 1.0], dtype=np.float32), identities
    )
    assert match is None
    print(f"Orthogonal embedding (below threshold) -> match=None score={score:.3f}")

    match, score = rs.find_best_match(
        np.array([1.0, 0.0, 0.0], dtype=np.float32), []
    )
    assert match is None and score == 0.0
    print("Empty identities list -> (None, 0.0), as expected")

    match, score = rs.find_best_match(
        np.array([0.0, 0.0, 0.0], dtype=np.float32), identities
    )
    assert match is None and score == 0.0
    print("Zero-norm face embedding -> (None, 0.0), as expected")

    # A near-match that's close to but not quite two identities —
    # picks the strictly higher-scoring one.
    identities_close = [
        {"label": "A", "embedding": np.array([0.9, 0.1, 0.0], dtype=np.float32) / np.linalg.norm([0.9, 0.1, 0.0])},
        {"label": "B", "embedding": np.array([0.1, 0.9, 0.0], dtype=np.float32) / np.linalg.norm([0.1, 0.9, 0.0])},
    ]
    match, score = rs.find_best_match(
        np.array([1.0, 0.0, 0.0], dtype=np.float32), identities_close
    )
    assert match["label"] == "A"
    print(f"Picks the higher-scoring of two plausible matches -> {match['label']} ({score:.3f})")

    # ------------------------------------------------------------
    # recognize_embedding — watchlist targets take priority over
    # students, which take priority over guests; falls through to
    # UNKNOWN when nothing matches
    # ------------------------------------------------------------

    # Directly inject cache contents rather than hitting a real DB —
    # and freeze last_refresh so refresh_if_needed() (10s interval)
    # doesn't wipe this out with an empty real-DB refresh mid-test.
    import time

    student_embedding = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    guest_embedding = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    target_embedding = np.array([0.0, 0.0, -1.0], dtype=np.float32)

    rs.identity_cache.students = [{
        "student_id": "STU-1",
        "full_name": "Alice Example",
        "admission_number": "ADM-1",
        "hostel": "Nyayo",
        "room": "A1",
        "embedding": student_embedding,
    }]
    rs.identity_cache.guests = [{
        "guest_id": "AG-1",
        "expires_at": __import__("datetime").datetime.now() + __import__("datetime").timedelta(hours=1),
        "embedding": guest_embedding,
    }]
    rs.identity_cache.targets = [{
        "target_id": "TGT-1",
        "full_name": "Person Of Interest",
        "reason": "Reported theft",
        "embedding": target_embedding,
    }]
    rs.identity_cache.last_refresh = time.time()

    student_result = rs.recognize_embedding(student_embedding)
    assert student_result["status"] == "STUDENT"
    assert student_result["student_id"] == "STU-1"
    print("Matches the student cache entry ->", student_result)

    guest_result = rs.recognize_embedding(guest_embedding)
    assert guest_result["status"] == "ADMITTED_GUEST"
    assert guest_result["guest_id"] == "AG-1"
    print("Matches the guest cache entry (no student match) ->", guest_result)

    target_result = rs.recognize_embedding(target_embedding)
    assert target_result["status"] == "TARGET_MATCH"
    assert target_result["target_id"] == "TGT-1"
    assert target_result["full_name"] == "Person Of Interest"
    assert target_result["reason"] == "Reported theft"
    print("Matches the watchlist target cache entry ->", target_result)

    # [0,0,1] is orthogonal to student/guest and anti-parallel to
    # the target embedding [0,0,-1] (score -1, well under threshold)
    # — genuinely matches nothing in any of the three caches.
    unknown_embedding = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    unknown_result = rs.recognize_embedding(unknown_embedding)
    assert unknown_result["status"] == "UNKNOWN"
    print("No match in any cache -> UNKNOWN ->", unknown_result)

    # A face that would match a guest AND look somewhat like the
    # student vector: students are checked first, so a genuine
    # student match always wins even when a guest is also present.
    rs.identity_cache.last_refresh = time.time()
    dual_match_result = rs.recognize_embedding(student_embedding)
    assert dual_match_result["status"] == "STUDENT"
    print("Student match takes priority over any guest match")

    # A watchlisted target wins even over a face that's also a
    # verified student — a target flag is a security override
    # (docs/PRD.md §8's "target tracking"), so add a target entry
    # sharing the student's exact embedding and confirm it wins.
    rs.identity_cache.targets = rs.identity_cache.targets + [{
        "target_id": "TGT-2",
        "full_name": "Flagged Student",
        "reason": "Under investigation",
        "embedding": student_embedding,
    }]
    rs.identity_cache.last_refresh = time.time()
    override_result = rs.recognize_embedding(student_embedding)
    assert override_result["status"] == "TARGET_MATCH"
    assert override_result["target_id"] == "TGT-2"
    print("A target flag overrides an otherwise-legitimate student match ->", override_result)

    # Reset targets to just the original entry for the remaining tests.
    rs.identity_cache.targets = [{
        "target_id": "TGT-1",
        "full_name": "Person Of Interest",
        "reason": "Reported theft",
        "embedding": target_embedding,
    }]
    rs.identity_cache.last_refresh = time.time()

    # ------------------------------------------------------------
    # recognize_face — combines identity match with liveness
    # ------------------------------------------------------------

    rs.identity_cache.last_refresh = time.time()

    live_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    live_face = FakeFace(embedding=student_embedding)

    combined = rs.recognize_face(live_frame, live_face)
    assert combined["status"] == "STUDENT"
    assert "is_live" in combined
    assert "liveness_score" in combined
    print("recognize_face merges identity + liveness fields ->", {
        k: combined[k] for k in ("status", "is_live", "liveness_score")
    })

    # ------------------------------------------------------------
    # recognize_image — NO_FACE cases, then delegates to recognize_face
    # ------------------------------------------------------------

    no_image_result = rs.recognize_image(None)
    assert no_image_result == {"status": "NO_FACE", "message": "No image provided"}
    print("recognize_image(None) -> NO_FACE, as expected")

    _queue_faces([])
    no_face_result = rs.recognize_image(live_frame)
    assert no_face_result["status"] == "NO_FACE"
    print("recognize_image with no detected faces -> NO_FACE, as expected")

    rs.identity_cache.last_refresh = time.time()
    _queue_faces([live_face])
    full_result = rs.recognize_image(live_frame)
    assert full_result["status"] == "STUDENT"
    print("recognize_image with a detected, matching face -> STUDENT ->", {
        k: full_result[k] for k in ("status", "is_live")
    })

    import shutil
    shutil.rmtree(temp_dir)

    print("\nrecognition_service smoke test passed.")
