import sqlite3

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# A persisted camera *registry* for the admin dashboards
# (docs/PRD.md §8): Original Admin gets full camera management
# control, Security Admin gets access/configuration within
# SmartAccess, and the Dean of School gets read-only "venue camera
# access" scoped to their department.
#
# This is deliberately separate from src/camera/camera_manager.py,
# which is a runtime in-memory manager that spins up CameraWorker
# threads against real camera hardware/RTSP streams for the live
# recognition pipeline — it holds no persisted state and isn't
# reachable from the API. This table is the other half: a
# database-backed record of which cameras exist, where, and their
# admin-reported status, independent of whether the recognition
# pipeline currently has a live worker running for them. Wiring a
# registry row to an actual running CameraWorker (so `status`
# reflects reality instead of being admin-set) is future work once
# real camera hardware/streams are deployed.
#
# `source` (an RTSP URL or webcam index) is stored as plain text
# like everything else here for now — no credentials are handled by
# this layer, consistent with holding anything credential-related
# until real infrastructure is available.


# Which Smart Gen product a camera belongs to: CHECKPOINT cameras
# are SmartAccess (checkpoints/gates); CLASSROOM cameras are
# SmartAttendance. src/api/main.py's CameraRequest requires
# location and source (the IP camera's RTSP/HTTP stream address)
# at creation for the same reason — a camera registry entry only
# means something once you know which product it serves, where it
# physically is, and how to reach it.
CAMERA_TYPES = {
    "CHECKPOINT",
    "CLASSROOM"
}

STATUSES = {
    "ONLINE",
    "OFFLINE",
    "MAINTENANCE"
}


def _row_to_dict(row):

    if row is None:

        return None

    result = dict(row)

    if "enabled" in result:

        result["enabled"] = bool(result["enabled"])

    return result


def create_camera(
    camera_id,
    name,
    camera_type,
    location=None,
    department=None,
    source=None,
    created_by=None
):

    camera_type = camera_type.upper()

    if camera_type not in CAMERA_TYPES:

        raise ValueError(
            f"Unknown camera_type: {camera_type}"
        )

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute("""
            INSERT INTO cameras (
                camera_id,
                name,
                camera_type,
                location,
                department,
                source,
                status,
                enabled,
                created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, 'OFFLINE', 1, ?)
        """, (
            camera_id,
            name,
            camera_type,
            location,
            department,
            source,
            created_by
        ))

        connection.commit()

    except Exception as error:

        connection.close()

        raise ValueError(
            f"Could not create camera — camera_id may already "
            f"exist ({error})"
        )

    connection.close()

    return {

        "camera_id": camera_id,

        "name": name,

        "camera_type": camera_type,

        "location": location,

        "department": department,

        "source": source,

        "status": "OFFLINE",

        "enabled": True,

        "created_by": created_by
    }


def list_cameras(camera_type=None, department=None, status=None):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    query = "SELECT * FROM cameras WHERE 1=1"

    params = []

    if camera_type:

        query += " AND camera_type = ?"

        params.append(camera_type.upper())

    if department:

        query += " AND department = ?"

        params.append(department)

    if status:

        query += " AND status = ?"

        params.append(status.upper())

    query += " ORDER BY camera_type, name"

    cursor.execute(query, params)

    rows = cursor.fetchall()

    connection.close()

    return [
        _row_to_dict(row)
        for row in rows
    ]


def get_camera(camera_id):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM cameras WHERE camera_id = ?",
        (camera_id,)
    )

    row = cursor.fetchone()

    connection.close()

    return _row_to_dict(row)


def update_camera(camera_id, name=None, location=None, source=None, enabled=None):

    fields = []
    params = []

    if name is not None:
        fields.append("name = ?")
        params.append(name)

    if location is not None:
        fields.append("location = ?")
        params.append(location)

    if source is not None:
        fields.append("source = ?")
        params.append(source)

    if enabled is not None:
        fields.append("enabled = ?")
        params.append(1 if enabled else 0)

    if not fields:

        raise ValueError("No fields supplied to update.")

    params.append(camera_id)

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(f"""
        UPDATE cameras
        SET {", ".join(fields)}
        WHERE camera_id = ?
    """, params)

    connection.commit()

    updated = cursor.rowcount

    connection.close()

    return updated > 0


def update_status(camera_id, status):

    status = status.upper()

    if status not in STATUSES:

        raise ValueError(
            f"Unknown status: {status}"
        )

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE cameras
        SET status = ?
        WHERE camera_id = ?
    """, (
        status,
        camera_id
    ))

    connection.commit()

    updated = cursor.rowcount

    connection.close()

    return updated > 0


def delete_camera(camera_id):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM cameras
        WHERE camera_id = ?
    """, (
        camera_id,
    ))

    connection.commit()

    deleted = cursor.rowcount

    connection.close()

    return deleted > 0
