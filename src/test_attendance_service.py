import os
from src.services import template_store as _template_store

# Templates are always written encrypted; give the test its own key.
os.environ.setdefault(
    "TEMPLATE_ENCRYPTION_KEYS", _template_store.generate_key()
)
import sys
import sqlite3
import tempfile
import types
from datetime import datetime, timedelta

import numpy as np


# ============================================================
# FAKE `insightface` — same convention as test_enrollment_service.py /
# test_recognition_service.py: this sandbox has no real model weights,
# so this stands in for FaceAnalysis.
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

    connection.execute("""
        CREATE TABLE IF NOT EXISTS timetable_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id INTEGER,
            unit_code TEXT,
            course TEXT NOT NULL,
            year INTEGER NOT NULL,
            department TEXT,
            semester INTEGER,
            lecturer_id TEXT,
            day_of_week TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            unit_name TEXT NOT NULL,
            facilitator TEXT,
            venue TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ON',
            created_by TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            camera_type TEXT NOT NULL,
            location TEXT,
            department TEXT,
            source TEXT,
            status TEXT NOT NULL DEFAULT 'OFFLINE',
            enabled BOOLEAN NOT NULL DEFAULT 1,
            created_by TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS class_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timetable_entry_id INTEGER NOT NULL,
            session_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            activates_at DATETIME NOT NULL,
            cutoff_at DATETIME NOT NULL,
            submit_at DATETIME NOT NULL,
            submitted_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (timetable_entry_id, session_date)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_session_id INTEGER NOT NULL,
            student_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ABSENT',
            recognized_at DATETIME,
            recognition_score REAL,
            UNIQUE (class_session_id, student_id)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS attendance_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            class_session_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            unit_name TEXT NOT NULL,
            facilitator TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            read_at DATETIME
        )
    """)

    connection.commit()
    connection.close()


def _insert_student(db_path, student_id, full_name, admission_number,
                     course, year, department=None, semester=None,
                     embedding_file=None):

    connection = sqlite3.connect(db_path)
    connection.execute(
        "INSERT INTO students (student_id, full_name, admission_number, "
        "hostel, room, department, course, year, semester, embedding_file) "
        "VALUES (?, ?, ?, 'Nyayo', 'A1', ?, ?, ?, ?, ?)",
        (student_id, full_name, admission_number, department, course,
         year, semester, embedding_file)
    )
    connection.commit()
    connection.close()


def _insert_entry(db_path, day_of_week, start_time, end_time, venue,
                   status="ON", course="BSc Computer Science", year=2,
                   department=None, semester=1, unit_name="Data Structures",
                   facilitator="Dr. Otieno"):

    connection = sqlite3.connect(db_path)
    cursor = connection.execute(
        "INSERT INTO timetable_entries (course, year, department, semester, "
        "day_of_week, start_time, end_time, unit_name, facilitator, venue, "
        "status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (course, year, department, semester, day_of_week, start_time,
         end_time, unit_name, facilitator, venue, status)
    )
    entry_id = cursor.lastrowid
    connection.commit()
    connection.close()
    return entry_id


def _save_embedding(embeddings_dir, filename, vector):
    os.makedirs(embeddings_dir, exist_ok=True)
    embedding = np.array(vector, dtype=np.float32)
    embedding = embedding / np.linalg.norm(embedding)
    _template_store.save_template(
        os.path.join(embeddings_dir, filename), embedding
    )


if __name__ == "__main__":

    print("Testing attendance_service against a faked InsightFace...")

    _install_fake_insightface()

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")
    temp_embeddings_dir = os.path.join(temp_dir, "embeddings")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    import src.services.recognition_service as recognition_service
    recognition_service.STUDENT_EMBEDDINGS_FOLDER = temp_embeddings_dir

    from src.services import attendance_service
    attendance_service.STUDENT_EMBEDDINGS_FOLDER = temp_embeddings_dir

    attendance_service.check_liveness = (
        lambda image, face: {
            "is_live": True,
            "liveness_score": 0.9,
            "reasons": []
        }
    )

    blank_image = np.zeros((100, 100, 3), dtype=np.uint8)

    # A fixed Wednesday, 10:00 class -> activates 09:40, cutoff 10:35,
    # submit 10:40. All "now" values below are relative to this.
    CLASS_DATE = datetime(2026, 9, 30)  # a Wednesday
    assert CLASS_DATE.strftime("%A").upper() == "WEDNESDAY"

    def at(hour, minute):
        return CLASS_DATE.replace(hour=hour, minute=minute)

    _insert_student(
        temp_db_path, "STU-1", "Alice Example", "ADM-1",
        course="BSc Computer Science", year=2, semester=1,
        embedding_file="STU-1.npy"
    )
    _insert_student(
        temp_db_path, "STU-2", "Bob Example", "ADM-2",
        course="BSc Computer Science", year=2, semester=1,
        embedding_file="STU-2.npy"
    )
    # Different course -> not on this class's roster at all.
    _insert_student(
        temp_db_path, "STU-3", "Carol Elsewhere", "ADM-3",
        course="BSc Mathematics", year=2, semester=1,
        embedding_file="STU-3.npy"
    )

    _save_embedding(temp_embeddings_dir, "STU-1.npy", [1.0, 0.0, 0.0])
    _save_embedding(temp_embeddings_dir, "STU-2.npy", [0.0, 1.0, 0.0])
    _save_embedding(temp_embeddings_dir, "STU-3.npy", [0.0, 0.0, 1.0])

    entry_id = _insert_entry(
        temp_db_path, day_of_week="WEDNESDAY", start_time="10:00",
        end_time="11:00", venue="Room 204"
    )

    # ------------------------------------------------------------
    # A session does not open before its activation time (09:40).
    # ------------------------------------------------------------

    connection = sqlite3.connect(temp_db_path)
    connection.row_factory = sqlite3.Row
    entry_row = connection.execute(
        "SELECT * FROM timetable_entries WHERE id = ?", (entry_id,)
    ).fetchone()

    too_early = attendance_service._get_or_open_session(
        connection.cursor(), entry_row, "2026-09-30", at(9, 30)
    )
    connection.close()
    assert too_early is None
    print("Session does not open before activates_at -> ok")

    # ------------------------------------------------------------
    # It opens exactly at activates_at (09:40).
    # ------------------------------------------------------------

    connection = sqlite3.connect(temp_db_path)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    session = attendance_service._get_or_open_session(
        cursor, entry_row, "2026-09-30", at(9, 40)
    )
    connection.commit()
    connection.close()

    assert session is not None
    assert session["status"] == "ACTIVE"
    session_id = session["id"]
    print("Session opens at activates_at ->", dict(session))

    # ------------------------------------------------------------
    # record_attendance: a matching face before cutoff (10:35) is
    # accepted; a repeat sighting of the same student is a no-op.
    # ------------------------------------------------------------

    _queue_faces([_FakeFace([1.0, 0.0, 0.0])])  # matches STU-1
    result = attendance_service.record_attendance(session_id, blank_image)
    assert result["status"] == "STUDENT"
    assert result["student_id"] == "STU-1"
    assert result["already_recorded"] is False
    print("First sighting of STU-1 recorded ->", result)

    _queue_faces([_FakeFace([1.0, 0.0, 0.0])])  # STU-1 again
    result = attendance_service.record_attendance(session_id, blank_image)
    assert result["status"] == "STUDENT"
    assert result["already_recorded"] is True
    print("Repeat sighting of STU-1 is a no-op ->", result)

    connection = sqlite3.connect(temp_db_path)
    count = connection.execute(
        "SELECT COUNT(*) FROM attendance_records WHERE class_session_id = ?",
        (session_id,)
    ).fetchone()[0]
    connection.close()
    assert count == 1
    print("Exactly one attendance_records row for STU-1 -> ok")

    # ------------------------------------------------------------
    # A face that doesn't match anyone on the roster (STU-3, a
    # different course) is UNKNOWN, not recorded.
    # ------------------------------------------------------------

    _queue_faces([_FakeFace([0.0, 0.0, 1.0])])  # STU-3's embedding
    result = attendance_service.record_attendance(session_id, blank_image)
    assert result["status"] == "UNKNOWN"
    print("A face outside the expected roster is UNKNOWN ->", result)

    # ------------------------------------------------------------
    # A spoofed (liveness-failed) face is rejected, not recorded.
    # ------------------------------------------------------------

    attendance_service.check_liveness = (
        lambda image, face: {
            "is_live": False,
            "liveness_score": 0.1,
            "reasons": ["texture_out_of_expected_range"]
        }
    )
    _queue_faces([_FakeFace([0.0, 1.0, 0.0])])  # would otherwise match STU-2
    result = attendance_service.record_attendance(session_id, blank_image)
    assert result["status"] == "LIVENESS_FAILED"
    print("Spoofed face rejected ->", result)

    connection = sqlite3.connect(temp_db_path)
    stu2_recorded = connection.execute(
        "SELECT COUNT(*) FROM attendance_records "
        "WHERE class_session_id = ? AND student_id = 'STU-2'",
        (session_id,)
    ).fetchone()[0]
    connection.close()
    assert stu2_recorded == 0
    print("STU-2 still has no attendance record -> ok")

    # Restore a passing liveness check for the rest of the test.
    attendance_service.check_liveness = (
        lambda image, face: {
            "is_live": True,
            "liveness_score": 0.9,
            "reasons": []
        }
    )

    # ------------------------------------------------------------
    # get_active_session_for_camera: resolves via the camera's
    # location matching the entry's venue, and stops handing back a
    # session once "now" is past cutoff_at (PRD rule 5) — a frame
    # recognized after 10:35 must never be able to mark someone
    # present, even if it would otherwise match.
    # ------------------------------------------------------------

    connection = sqlite3.connect(temp_db_path)
    connection.execute(
        "INSERT INTO cameras (camera_id, name, camera_type, location, "
        "status, enabled) VALUES ('CAM-1', 'Room 204 Cam', 'CLASSROOM', "
        "'Room 204', 'ONLINE', 1)"
    )
    connection.commit()
    connection.close()

    resolved = attendance_service.get_active_session_for_camera(
        "CAM-1", now=at(10, 0)
    )
    assert resolved is not None
    assert resolved["id"] == session_id
    print("get_active_session_for_camera resolves the right session ->",
          dict(resolved))

    too_late = attendance_service.get_active_session_for_camera(
        "CAM-1", now=at(10, 36)
    )
    assert too_late is None
    print("get_active_session_for_camera refuses a frame past cutoff_at -> ok")

    # ------------------------------------------------------------
    # run_sweep at submit_at (10:40): STU-2 (never seen, liveness
    # failure doesn't count) is marked ABSENT; STU-1 stays PRESENT;
    # STU-3 (different course, never on this roster) gets nothing.
    # One notification per expected student, right kind each.
    # ------------------------------------------------------------

    sweep_result = attendance_service.run_sweep(now=at(10, 40))
    assert session_id in sweep_result["submitted_session_ids"]
    print("run_sweep submitted the session ->", sweep_result)

    connection = sqlite3.connect(temp_db_path)
    connection.row_factory = sqlite3.Row
    records = {
        row["student_id"]: row["status"]
        for row in connection.execute(
            "SELECT student_id, status FROM attendance_records "
            "WHERE class_session_id = ?", (session_id,)
        ).fetchall()
    }
    session_status = connection.execute(
        "SELECT status FROM class_sessions WHERE id = ?", (session_id,)
    ).fetchone()["status"]
    notifications = {
        row["student_id"]: row["kind"]
        for row in connection.execute(
            "SELECT student_id, kind FROM attendance_notifications "
            "WHERE class_session_id = ?", (session_id,)
        ).fetchall()
    }
    connection.close()

    assert records == {"STU-1": "PRESENT", "STU-2": "ABSENT"}
    assert session_status == "SUBMITTED"
    assert notifications == {"STU-1": "ATTENDED", "STU-2": "MISSED"}
    print("Final roll ->", records, "| notifications ->", notifications)

    # ------------------------------------------------------------
    # A POSTPONED entry never gets a session opened, even well within
    # what would otherwise be its activation window.
    # ------------------------------------------------------------

    postponed_entry_id = _insert_entry(
        temp_db_path, day_of_week="WEDNESDAY", start_time="14:00",
        end_time="15:00", venue="Room 305", status="POSTPONED"
    )

    sweep_result = attendance_service.run_sweep(now=at(13, 45))
    connection = sqlite3.connect(temp_db_path)
    postponed_sessions = connection.execute(
        "SELECT COUNT(*) FROM class_sessions WHERE timetable_entry_id = ?",
        (postponed_entry_id,)
    ).fetchone()[0]
    connection.close()
    assert postponed_sessions == 0
    print("A POSTPONED entry never gets a session opened -> ok")

    import shutil
    shutil.rmtree(temp_dir)

    print("\nattendance_service smoke test passed.")
