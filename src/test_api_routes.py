import os
import sqlite3
import tempfile

import cv2
import numpy as np

# Drives the real FastAPI app over HTTP (no server needed) with the
# same faked InsightFace the service tests use. Needs `httpx` for
# FastAPI's TestClient — a test-only dependency, so it isn't in
# requirements.txt: `pip install httpx`.
#
# Why this exists: every other test here calls a service function
# directly, which is how two real bugs got through — a missing import
# in src/api/main.py, and multipart endpoints reading their fields from
# the query string instead of the form the web dashboard sends.

from src.test_enrollment_service import (
    _FakeFace,
    _create_schema,
    _install_fake_insightface,
    _queue_faces,
)


def _png_bytes():
    ok, encoded = cv2.imencode(".png", np.zeros((60, 60, 3), np.uint8))
    assert ok
    return encoded.tobytes()


def _extra_schema(path):

    connection = sqlite3.connect(path)

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

    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing the real API routes over HTTP...")

    _install_fake_insightface()

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")
    temp_embeddings_dir = os.path.join(temp_dir, "embeddings")
    os.makedirs(temp_embeddings_dir, exist_ok=True)

    _create_schema(temp_db_path)
    _extra_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    import src.services.recognition_service as recognition_service
    recognition_service.STUDENT_EMBEDDINGS_FOLDER = temp_embeddings_dir

    from src.services import enrollment_service
    enrollment_service.STUDENT_EMBEDDINGS_FOLDER = temp_embeddings_dir
    enrollment_service.check_liveness = lambda image, face: {
        "is_live": True, "liveness_score": 0.9, "reasons": []
    }

    from src.services.auth_service import create_access_token
    import src.api.main as main
    from fastapi.testclient import TestClient

    client = TestClient(main.app)

    admin = {"Authorization": "Bearer " + create_access_token(
        "admin1", "ADMIN", "ORIGINAL")}
    student = {"Authorization": "Bearer " + create_access_token(
        "dan.bare", "STUDENT", None)}

    png = _png_bytes()

    # ------------------------------------------------------------
    # STRUCTURAL: no multipart upload route may take plain scalar
    # parameters — next to a File they're read from the query string.
    # ------------------------------------------------------------

    checked = 0
    for route in main.app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        has_file = any(
            getattr(param.field_info, "annotation", None) is not None
            and "UploadFile" in str(param.field_info.annotation)
            for param in dependant.body_params
        )
        if has_file:
            checked += 1
            assert not dependant.query_params, (
                f"{route.path} reads {[p.name for p in dependant.query_params]} "
                "from the query string next to a file upload"
            )
    assert checked >= 4
    print(f"{checked} file-upload routes read their fields from the form -> ok")

    # ------------------------------------------------------------
    # /enroll/student-face (admin): form fields work, and consent is
    # enforced and recorded.
    # ------------------------------------------------------------

    fields = {
        "student_id": "STU-1",
        "full_name": "Amina Wanjiru",
        "admission_number": "ADM-1",
        "hostel": "Hostel A",
        "room": "A12",
    }

    _queue_faces([_FakeFace([1.0, 0.0, 0.0])])
    response = client.post(
        "/enroll/student-face", headers=admin, data=fields,
        files=[("files", ("p.png", png, "image/png"))],
    )
    assert response.status_code == 403, response.text
    print("Admin enrollment without consent_confirmed -> 403 ->", response.json())

    response = client.post(
        "/enroll/student-face", headers=admin,
        data={**fields, "consent_confirmed": "true"},
        files=[("files", ("p.png", png, "image/png"))],
    )
    assert response.status_code == 200, response.text
    assert response.json()["student_id"] == "STU-1"
    print("Admin enrollment with form fields + consent -> 200")

    connection = sqlite3.connect(temp_db_path)
    consent = connection.execute(
        "SELECT channel, recorded_by FROM biometric_consents "
        "WHERE student_id = 'STU-1'"
    ).fetchone()
    connection.close()
    assert consent == ("ADMIN_ASSISTED", "admin1")
    print("Consent recorded against the confirming admin ->", consent)

    # ------------------------------------------------------------
    # /watchlist: its fields are form fields too
    # ------------------------------------------------------------

    response = client.post(
        "/watchlist", headers=admin,
        data={"full_name": "Person Of Interest", "reason": "Reported theft"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["full_name"] == "Person Of Interest"
    assert response.json()["reason"] == "Reported theft"
    print("POST /watchlist keeps its form fields ->", response.json()["target_id"])

    # ------------------------------------------------------------
    # Student self-service consent flow, end to end
    # ------------------------------------------------------------

    response = client.post("/students", headers=admin, json={
        "student_id": "STU-200", "full_name": "Dan Bare",
        "admission_number": "ADM-200", "hostel": "Nyayo", "room": "B1",
    })
    assert response.status_code == 200, response.text
    print("POST /students works (was a NameError before) -> 200")

    connection = sqlite3.connect(temp_db_path)
    connection.execute(
        "INSERT INTO users (username, linked_person_id) "
        "VALUES ('dan.bare', 'STU-200')"
    )
    connection.commit()
    connection.close()

    # Admin-only and student-only doors stay shut.
    assert client.get("/me/consent", headers=admin).status_code == 403
    assert client.get("/me/consent").status_code == 401

    body = client.get("/me/consent", headers=student).json()
    assert body["status"]["consent_active"] is False
    assert body["notice"]["version"] == body["status"]["current_notice_version"]
    assert len(body["notice"]["sections"]) >= 4
    version = body["notice"]["version"]
    print("GET /me/consent -> notice", version, "and no consent yet")

    _queue_faces([_FakeFace([0.2, 0.3, 0.4])])
    response = client.post(
        "/me/enroll-face", headers=student,
        files=[("files", ("p.png", png, "image/png"))],
    )
    assert response.status_code == 403, response.text
    print("Self-enroll before consenting -> 403 ->", response.json())

    response = client.post(
        "/me/consent", headers=student, json={"notice_version": "old-v0"}
    )
    assert response.status_code == 409, response.text
    print("Consent against a stale notice version -> 409")

    response = client.post(
        "/me/consent", headers=student, json={"notice_version": version}
    )
    assert response.status_code == 200, response.text
    assert response.json()["consent_active"] is True
    assert response.json()["channel"] == "SELF"
    print("POST /me/consent -> active, channel SELF")

    _queue_faces([_FakeFace([0.2, 0.3, 0.4])])
    response = client.post(
        "/me/enroll-face", headers=student,
        files=[("files", ("p.png", png, "image/png"))],
    )
    assert response.status_code == 200, response.text
    print("Self-enroll after consenting -> 200 (was a NameError before)")

    students = {s["student_id"]: s for s in
                client.get("/students", headers=admin).json()}
    assert students["STU-200"]["face_enrolled"] is True
    assert students["STU-200"]["consent_recorded"] is True
    assert students["STU-1"]["consent_recorded"] is True
    print("GET /students reports face_enrolled + consent_recorded")

    # A face enrolled before consent recording existed shows as a gap.
    connection = sqlite3.connect(temp_db_path)
    connection.execute(
        "INSERT INTO students (student_id, full_name, admission_number, "
        "hostel, room, embedding_file) "
        "VALUES ('STU-LEGACY', 'Legacy', 'ADM-L', 'Nyayo', 'C1', 'L.npy')"
    )
    connection.commit()
    connection.close()
    students = {s["student_id"]: s for s in
                client.get("/students", headers=admin).json()}
    assert students["STU-LEGACY"]["face_enrolled"] is True
    assert students["STU-LEGACY"]["consent_recorded"] is False
    print("A pre-consent legacy enrollment is visible as consent_recorded=false")

    template = os.path.join(temp_embeddings_dir, "STU-200.npy")
    assert os.path.exists(template)

    response = client.post("/me/consent/withdraw", headers=student)
    assert response.status_code == 200, response.text
    assert response.json()["face_data_deleted"] is True
    assert not os.path.exists(template)
    print("POST /me/consent/withdraw -> template deleted ->", response.json())

    status = client.get("/me/consent", headers=student).json()["status"]
    assert status["consent_active"] is False
    profile = client.get("/me", headers=student).json()
    assert profile["face_enrolled"] is False
    print("After withdrawal: consent inactive, face_enrolled false")

    _queue_faces([_FakeFace([0.2, 0.3, 0.4])])
    response = client.post(
        "/me/enroll-face", headers=student,
        files=[("files", ("p.png", png, "image/png"))],
    )
    assert response.status_code == 403
    print("Re-enrolling after withdrawal needs fresh consent -> 403")

    import shutil
    shutil.rmtree(temp_dir)

    print("\nAPI routes smoke test passed.")
