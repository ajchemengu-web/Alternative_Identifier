import os
import sqlite3
import tempfile


def _create_schema(path):

    connection = sqlite3.connect(path)

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

    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing camera_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    from src.services import camera_service

    # ------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------

    gate_camera = camera_service.create_camera(
        camera_id="CAM-GATE-1",
        name="Main Gate",
        camera_type="checkpoint",
        location="Main Gate",
        source="rtsp://example.invalid/gate1",
        created_by="original_admin"
    )

    assert gate_camera["camera_type"] == "CHECKPOINT"
    assert gate_camera["status"] == "OFFLINE"
    assert gate_camera["enabled"] is True
    print("Created checkpoint camera ->", gate_camera)

    classroom_camera = camera_service.create_camera(
        camera_id="CAM-LT3-1",
        name="Lecture Theatre 3",
        camera_type="CLASSROOM",
        location="LT 3",
        department="School of Computing",
        created_by="original_admin"
    )

    assert classroom_camera["camera_type"] == "CLASSROOM"
    print("Created classroom camera ->", classroom_camera)

    try:
        camera_service.create_camera(
            camera_id="CAM-BAD",
            name="Bad camera",
            camera_type="NOT_A_TYPE"
        )
        raise AssertionError("Expected ValueError for invalid camera_type")
    except ValueError as error:
        print("Invalid camera_type rejected as expected:", error)

    try:
        camera_service.create_camera(
            camera_id="CAM-GATE-1",
            name="Duplicate gate camera",
            camera_type="CHECKPOINT"
        )
        raise AssertionError("Expected ValueError for duplicate camera_id")
    except ValueError as error:
        print("Duplicate camera_id rejected as expected:", error)

    # ------------------------------------------------------------
    # LIST / FILTER
    # ------------------------------------------------------------

    all_cameras = camera_service.list_cameras()
    assert len(all_cameras) == 2
    print(f"All cameras: {len(all_cameras)}")

    checkpoint_only = camera_service.list_cameras(camera_type="checkpoint")
    assert len(checkpoint_only) == 1
    assert checkpoint_only[0]["camera_id"] == "CAM-GATE-1"
    print(f"Checkpoint cameras: {len(checkpoint_only)}")

    department_only = camera_service.list_cameras(
        department="School of Computing"
    )
    assert len(department_only) == 1
    assert department_only[0]["camera_id"] == "CAM-LT3-1"
    print(f"Department-filtered cameras: {len(department_only)}")

    no_match = camera_service.list_cameras(department="School of Business")
    assert no_match == []
    print("Non-matching department filter returns empty, as expected")

    # ------------------------------------------------------------
    # UPDATE STATUS
    # ------------------------------------------------------------

    updated = camera_service.update_status("CAM-GATE-1", "online")
    assert updated is True

    refreshed = camera_service.list_cameras(camera_type="CHECKPOINT")
    assert refreshed[0]["status"] == "ONLINE"
    print("Status updated to ONLINE ->", refreshed[0])

    missing_update = camera_service.update_status("CAM-MISSING", "ONLINE")
    assert missing_update is False
    print("Updating a non-existent camera's status returns False, as expected")

    try:
        camera_service.update_status("CAM-GATE-1", "NOT_A_REAL_STATUS")
        raise AssertionError("Expected ValueError for invalid status")
    except ValueError as error:
        print("Invalid status rejected as expected:", error)

    # ------------------------------------------------------------
    # UPDATE CONFIG (name/location/source/enabled)
    # ------------------------------------------------------------

    config_updated = camera_service.update_camera(
        "CAM-GATE-1",
        location="Main Gate (North Entrance)",
        enabled=False
    )
    assert config_updated is True

    refreshed = camera_service.list_cameras(camera_type="CHECKPOINT")
    assert refreshed[0]["location"] == "Main Gate (North Entrance)"
    assert refreshed[0]["enabled"] is False
    print("Config updated ->", refreshed[0])

    missing_config_update = camera_service.update_camera(
        "CAM-MISSING",
        name="X"
    )
    assert missing_config_update is False
    print("Updating a non-existent camera's config returns False, as expected")

    try:
        camera_service.update_camera("CAM-GATE-1")
        raise AssertionError("Expected ValueError when no fields supplied")
    except ValueError as error:
        print("No-op update rejected as expected:", error)

    # ------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------

    deleted = camera_service.delete_camera("CAM-LT3-1")
    assert deleted is True

    missing_delete = camera_service.delete_camera("CAM-LT3-1")
    assert missing_delete is False

    assert len(camera_service.list_cameras()) == 1
    print("Delete removed the camera and is idempotent-safe (second delete -> False)")

    import shutil
    shutil.rmtree(temp_dir)

    print("\ncamera_service smoke test passed.")
