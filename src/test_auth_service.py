import os
import sqlite3
import tempfile
from datetime import datetime, timedelta

import src.db as db


def _create_users_table(path):

    connection = sqlite3.connect(path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL,
            admin_tier TEXT,
            linked_person_id TEXT,
            location TEXT,
            temp_expires_at DATETIME,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing auth_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_users_table(temp_db_path)

    # Point src.db at the temp database instead of data/smarthostel.db
    # for the duration of this test, so nothing here touches the real
    # tracked local dev database.
    db.DATABASE_PATH = temp_db_path

    from src.services import auth_service

    # ------------------------------------------------------------
    # ENROLL A STUDENT
    # ------------------------------------------------------------

    student = auth_service.create_user(
        username="jdoe",
        password="correct horse battery staple",
        email="jdoe@example.com",
        role="STUDENT",
        linked_person_id="STU-001"
    )

    assert student["dashboard"] == "smartattendance_app"
    print("Student enrollment ->", student)

    # ------------------------------------------------------------
    # LOGIN: correct vs wrong password
    # ------------------------------------------------------------

    ok = auth_service.authenticate("jdoe", "correct horse battery staple")
    assert ok is not None
    assert ok["role"] == "STUDENT"
    print("Correct password login ->", ok)

    bad = auth_service.authenticate("jdoe", "wrong password")
    assert bad is None
    print("Wrong password login -> rejected as expected")

    # ------------------------------------------------------------
    # ENROLL AN ORIGINAL ADMIN
    # ------------------------------------------------------------

    admin = auth_service.create_user(
        username="root_admin",
        password="another-strong-password",
        email="admin@example.com",
        role="ADMIN",
        admin_tier="ORIGINAL"
    )

    assert admin["dashboard"] == "original_admin_dashboard"
    print("Original admin enrollment ->", admin)

    # ------------------------------------------------------------
    # TEMPORARY ADMIN: expiry-based rejection
    # ------------------------------------------------------------

    expired_at = (
        datetime.now() - timedelta(minutes=1)
    ).isoformat()

    auth_service.create_user(
        username="temp_helper",
        password="temp-password",
        email="temp@example.com",
        role="ADMIN",
        admin_tier="TEMPORARY",
        temp_expires_at=expired_at
    )

    expired_login = auth_service.authenticate(
        "temp_helper",
        "temp-password"
    )

    assert expired_login is None
    print("Expired temporary admin -> rejected as expected")

    # ------------------------------------------------------------
    # TEMPORARY ADMIN: manual task-complete deactivation
    # ------------------------------------------------------------

    auth_service.create_user(
        username="temp_helper_2",
        password="temp-password-2",
        email="temp2@example.com",
        role="ADMIN",
        admin_tier="TEMPORARY"
    )

    still_active = auth_service.authenticate(
        "temp_helper_2",
        "temp-password-2"
    )

    assert still_active is not None
    assert still_active["dashboard"] == "enrollment_dashboard"

    result = auth_service.mark_temporary_admin_task_complete(
        "temp_helper_2"
    )

    assert result["success"] is True

    after_completion = auth_service.authenticate(
        "temp_helper_2",
        "temp-password-2"
    )

    assert after_completion is None
    print("Temporary admin deactivated after task completion, as expected")

    # ------------------------------------------------------------
    # INVALID ROLE / ADMIN_TIER COMBINATIONS ARE REJECTED
    # ------------------------------------------------------------

    try:
        auth_service.create_user(
            username="bad",
            password="x",
            email="bad@example.com",
            role="STUDENT",
            admin_tier="ORIGINAL"
        )
        raise AssertionError(
            "Expected ValueError for admin_tier on a non-admin role"
        )
    except ValueError:
        print("Rejected admin_tier on a non-ADMIN role, as expected")

    # ------------------------------------------------------------
    # GUARD ENROLLMENT REQUIRES A LOCATION (docs/PRD.md §6.2)
    # ------------------------------------------------------------

    try:
        auth_service.create_user(
            username="guard_no_location",
            password="x",
            email="guard_no_location@example.com",
            role="GUARD"
        )
        raise AssertionError(
            "Expected ValueError for a GUARD with no location"
        )
    except ValueError:
        print("Rejected a GUARD with no location, as expected")

    guard = auth_service.create_user(
        username="main_gate_guard",
        password="guard-password",
        email="guard@example.com",
        role="GUARD",
        location="Main Gate"
    )

    assert guard["location"] == "Main Gate"
    print("Guard enrollment ->", guard)

    guard_login = auth_service.authenticate(
        "main_gate_guard",
        "guard-password"
    )

    assert guard_login is not None
    assert guard_login["location"] == "Main Gate"
    print("Guard login carries their location ->", guard_login)

    os.remove(temp_db_path)
    os.rmdir(temp_dir)

    print("\nauth_service smoke test passed.")
