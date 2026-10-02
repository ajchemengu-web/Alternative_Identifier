import os
from src.services import template_store as _template_store

# Templates are always written encrypted; give the test its own key.
os.environ.setdefault(
    "TEMPLATE_ENCRYPTION_KEYS", _template_store.generate_key()
)
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

    # The shared enrollment-test users table is minimal (no role); erasure
    # matches on role = 'STUDENT'.
    connection.execute("ALTER TABLE users ADD COLUMN role TEXT")

    connection.executescript("""
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_type TEXT NOT NULL, person_identifier TEXT,
            entrance TEXT, decision TEXT
        );
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_session_id INTEGER NOT NULL, student_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ABSENT'
        );
        CREATE TABLE IF NOT EXISTS attendance_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL, class_session_id INTEGER NOT NULL,
            kind TEXT NOT NULL, unit_name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS data_erasure_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            erasure_reference TEXT UNIQUE NOT NULL, reason TEXT NOT NULL,
            erased_by TEXT NOT NULL, summary TEXT NOT NULL,
            performed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
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

    # An admin enrolling a face on someone's behalf can read the real
    # notice text to show them; anonymous callers can't.
    notice = client.get("/consent/notice", headers=admin)
    assert notice.status_code == 200
    assert notice.json()["version"]
    assert len(notice.json()["sections"]) >= 4
    assert client.get("/consent/notice").status_code == 401
    assert client.get("/consent/notice", headers=student).status_code == 200
    print("GET /consent/notice readable by admin + student, not anonymous")

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

    # ------------------------------------------------------------
    # Student data erasure (Original Admin only)
    # ------------------------------------------------------------

    original = admin
    dean = {"Authorization": "Bearer " + create_access_token(
        "dean1", "ADMIN", "DEAN")}
    security = {"Authorization": "Bearer " + create_access_token(
        "sec1", "ADMIN", "SECURITY")}

    # An id containing "/" — why the id travels in the query/body.
    weird_id = "SCI/2026/001"
    connection = sqlite3.connect(temp_db_path)
    connection.execute(
        "INSERT INTO students (student_id, full_name, admission_number, "
        "hostel, room, embedding_file) "
        "VALUES (?, 'Slash Student', 'ADM-SLASH', 'H', 'R', 'SCI-2026-001.npy')",
        (weird_id,)
    )
    connection.execute(
        "INSERT INTO access_logs (person_type, person_identifier, entrance, "
        "decision) VALUES ('STUDENT', ?, 'Main Gate', 'VERIFIED')", (weird_id,)
    )
    connection.commit()
    connection.close()
    np.save(os.path.join(temp_embeddings_dir, "SCI-2026-001.npy"),
            np.array([1.0, 0.0, 0.0], dtype=np.float32))

    # Only the Original Admin may ask, even for the read-only summary.
    for who, headers in [("anonymous", {}), ("student", student),
                         ("dean", dean), ("security admin", security)]:
        for call in (
            lambda h: client.get("/admin/students/data-summary",
                                 params={"student_id": weird_id}, headers=h),
            lambda h: client.post("/admin/students/erase", headers=h, json={
                "student_id": weird_id, "confirm": weird_id,
                "reason": "GRADUATED"}),
        ):
            assert call(headers).status_code in (401, 403), who
    print("Erasure endpoints reject anonymous, student, Dean, Security Admin")

    r = client.get("/admin/students/data-summary",
                   params={"student_id": weird_id}, headers=original)
    assert r.status_code == 200, r.text
    assert r.json()["access_log_entries"] == 1
    assert r.json()["face_template"] is True
    print("Summary works for an id containing slashes ->", r.json()["student_record"])

    assert client.get("/admin/students/data-summary",
                      params={"student_id": "NOBODY"},
                      headers=original).status_code == 404

    r = client.post("/admin/students/erase", headers=original, json={
        "student_id": weird_id, "confirm": "something else",
        "reason": "GRADUATED"})
    assert r.status_code == 400, r.text
    r = client.post("/admin/students/erase", headers=original, json={
        "student_id": weird_id, "confirm": weird_id, "reason": "Jane asked"})
    assert r.status_code == 400, r.text
    print("Wrong confirm / free-text reason -> 400")

    connection = sqlite3.connect(temp_db_path)
    connection.execute(
        "INSERT INTO watchlist_targets (target_id, full_name, status, "
        "linked_student_id) VALUES ('TGT-HOLD', 'Slash Student', 'ACTIVE', ?)",
        (weird_id,))
    connection.commit()
    connection.close()
    r = client.post("/admin/students/erase", headers=original, json={
        "student_id": weird_id, "confirm": weird_id, "reason": "GRADUATED"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["active_watchlist_targets"] == ["TGT-HOLD"]
    print("Active watchlist target -> 409 with the blocking ids")

    connection = sqlite3.connect(temp_db_path)
    connection.execute("UPDATE watchlist_targets SET status = 'RESOLVED'")
    connection.commit()
    connection.close()

    r = client.post("/admin/students/erase", headers=original, json={
        "student_id": weird_id, "confirm": weird_id, "reason": "GRADUATED"})
    assert r.status_code == 200, r.text
    assert r.json()["reason"] == "GRADUATED"
    assert r.json()["erasure_reference"]
    assert not os.path.exists(os.path.join(temp_embeddings_dir, "SCI-2026-001.npy"))
    print("Erased over HTTP ->", r.json()["erasure_reference"])

    connection = sqlite3.connect(temp_db_path)
    assert connection.execute(
        "SELECT COUNT(*) FROM students WHERE student_id = ?", (weird_id,)
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM access_logs WHERE person_identifier = ?", (weird_id,)
    ).fetchone()[0] == 0
    connection.close()

    assert client.post("/admin/students/erase", headers=original, json={
        "student_id": weird_id, "confirm": weird_id,
        "reason": "GRADUATED"}).status_code == 404
    print("Erasing again -> 404")

    # ------------------------------------------------------------
    # WHO MAY CALL WHAT: "any admin" is not enough for personal data.
    # A denied caller gets 403; an allowed one gets anything else (the
    # handler may then reject the empty request or hit a table this
    # test schema lacks — only the authorisation decision is checked).
    # ------------------------------------------------------------

    def _token(role, tier=None):
        return {"Authorization": "Bearer " + create_access_token(
            f"{role}-{tier}".lower(), role, tier,
            "School of Business" if tier == "DEAN" else None)}

    callers = {
        "ORIGINAL": _token("ADMIN", "ORIGINAL"),
        "SECURITY": _token("ADMIN", "SECURITY"),
        "TEMPORARY": _token("ADMIN", "TEMPORARY"),
        "TIMETABLING": _token("ADMIN", "TIMETABLING"),
        "DEAN": _token("ADMIN", "DEAN"),
        "GUARD": _token("GUARD"),
        "STUDENT": _token("STUDENT"),
        "LECTURER": _token("LECTURER"),
    }

    everyone = set(callers)
    admins = {"ORIGINAL", "SECURITY", "TEMPORARY", "TIMETABLING", "DEAN"}

    expected = {
        ("GET", "/students"): {"ORIGINAL", "SECURITY"},
        ("POST", "/students"): {"ORIGINAL", "SECURITY", "TEMPORARY"},
        ("GET", "/guests"): {"ORIGINAL", "SECURITY"},
        ("GET", "/access-logs"): {"ORIGINAL", "SECURITY", "GUARD"},
        ("PATCH", "/access-logs/1/false-positive"):
            {"ORIGINAL", "SECURITY", "GUARD"},
        ("GET", "/analytics/summary"): {"ORIGINAL", "SECURITY"},
        ("POST", "/recognize"): {"ORIGINAL", "SECURITY", "GUARD"},
        ("POST", "/attendance/recognize"): {"ORIGINAL"},
        ("GET", "/guard/pending"): {"ORIGINAL", "SECURITY", "GUARD"},
        ("POST", "/guard/admit/UNK-1"): {"ORIGINAL", "SECURITY", "GUARD"},
        ("POST", "/guard/reject/UNK-1"): {"ORIGINAL", "SECURITY", "GUARD"},
        # Creates accounts of any role/tier, admins included.
        ("POST", "/enroll"): {"ORIGINAL"},
        ("POST", "/enroll/student-face"):
            {"ORIGINAL", "SECURITY", "TEMPORARY"},
        ("GET", "/cameras"): {"ORIGINAL", "SECURITY", "DEAN"},
        ("GET", "/lecturers"): {"ORIGINAL", "TIMETABLING"},
        ("POST", "/lecturers"): {"ORIGINAL"},
        ("GET", "/units"): {"ORIGINAL", "TIMETABLING", "DEAN", "LECTURER"},
        ("GET", "/timetable"):
            {"ORIGINAL", "TIMETABLING", "DEAN", "STUDENT", "LECTURER"},
        ("GET", "/consent/notice"):
            {"ORIGINAL", "SECURITY", "TEMPORARY", "STUDENT"},
    }

    quiet = TestClient(main.app, raise_server_exceptions=False)

    for (method, path), allowed in expected.items():

        for who, headers in callers.items():

            status = quiet.request(method, path, headers=headers).status_code

            if who in allowed:
                assert status not in (401, 403), (
                    f"{who} should be allowed {method} {path}, got {status}")
            else:
                assert status == 403, (
                    f"{who} must be refused {method} {path}, got {status}")

    assert quiet.get("/students").status_code == 401
    assert admins <= everyone
    print(f"{len(expected)} endpoints x {len(callers)} callers: "
          "each tier gets exactly its own access")

    # ------------------------------------------------------------
    # DEAN SCOPING, end to end: the department is taken from the signed
    # token. Naming another department, or omitting it, cannot widen it.
    # ------------------------------------------------------------

    scope_connection = sqlite3.connect(temp_db_path)
    scope_connection.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            camera_type TEXT NOT NULL, location TEXT, department TEXT,
            source TEXT, status TEXT NOT NULL DEFAULT 'OFFLINE',
            enabled BOOLEAN NOT NULL DEFAULT 1, created_by TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    for camera_id, department in (("CAM-B", "School of Business"),
                                  ("CAM-L", "School of Law"),
                                  ("CAM-N", None)):
        scope_connection.execute(
            "INSERT INTO cameras (camera_id, name, camera_type, department) "
            "VALUES (?, ?, 'CLASSROOM', ?)", (camera_id, camera_id, department))
    for student_id, department in (("S-B", "School of Business"),
                                   ("S-L", "School of Law")):
        scope_connection.execute(
            "INSERT INTO students (student_id, full_name, admission_number, "
            "hostel, room, department, course, year) VALUES (?, ?, ?, 'H', "
            "'1', ?, 'C', 1)", (student_id, student_id, "ADM-" + student_id,
                                department))
    scope_connection.commit()
    scope_connection.close()

    def _dean_token(department):
        return {"Authorization": "Bearer " + create_access_token(
            "dean", "ADMIN", "DEAN", department)}

    dean = _dean_token("School of Business")

    def _ids(response, key):
        assert response.status_code == 200, response.text
        return {row[key] for row in response.json()}

    assert _ids(client.get("/cameras", headers=dean), "camera_id") == {"CAM-B"}
    assert _ids(client.get("/cameras?department=School of Business",
                           headers=dean), "camera_id") == {"CAM-B"}
    assert client.get("/cameras?department=School of Law",
                      headers=dean).status_code == 403
    assert _ids(client.get("/dean/roster", headers=dean),
                "student_id") == {"S-B"}
    assert client.get("/dean/roster?department=School of Law",
                      headers=dean).status_code == 403
    assert client.get("/dean/summary?department=School of Law",
                      headers=dean).status_code == 403
    for path in ("/timetable", "/units"):
        assert client.get(path + "?department=School of Law",
                          headers=dean).status_code == 403
    print("A Dean sees only their own department's cameras and roster; "
          "naming another is refused")

    no_department = _dean_token(None)
    for path in ("/cameras", "/dean/roster", "/dean/summary", "/timetable",
                 "/units"):
        assert client.get(path, headers=no_department).status_code == 403
    print("A Dean with no department on the account is refused everything")

    original_view = client.get("/dean/roster", headers=admin)
    assert {"S-B", "S-L"} <= _ids(original_view, "student_id")
    assert _ids(client.get("/cameras", headers=admin),
                "camera_id") == {"CAM-B", "CAM-L", "CAM-N"}
    assert _ids(client.get("/dean/roster?department=School of Law",
                           headers=admin), "student_id") == {"S-L"}
    print("The Original Admin still sees every department")

    # The route table itself: no personal-data route may be left open to
    # "any ADMIN" — that is how the Dean/Timetabling/Temporary tiers
    # ended up able to read every student and the access log.
    import inspect
    source = inspect.getsource(main)
    assert 'require_roles("ADMIN"' not in source, (
        "an endpoint is gated on role ADMIN alone (any tier)")
    print("No endpoint is gated on 'any ADMIN'")

    # The server refuses to start without an encryption key (and starts
    # with one) — the lifespan runs the check before anything else.
    import asyncio
    from src.services import template_store

    async def _enter_lifespan():
        async with main.lifespan(main.app):
            pass

    saved_keys = os.environ.pop(template_store.KEYS_ENV)
    try:
        try:
            asyncio.run(_enter_lifespan())
            raise AssertionError("Expected startup to be refused")
        except RuntimeError as error:
            assert "encryption is not configured" in str(error)
    finally:
        os.environ[template_store.KEYS_ENV] = saved_keys
    asyncio.run(_enter_lifespan())
    print("Startup refused without a template key; fine with one")

    import shutil
    shutil.rmtree(temp_dir)

    print("\nAPI routes smoke test passed.")
