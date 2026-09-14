import sqlite3

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# SmartAccess "scene reconstruction" (docs/PRD.md §8, Security Admin
# dashboard): given a location (an access_logs "entrance" value —
# see src/api/main.py's POST /recognize, which now resolves that
# from the registered camera a checkpoint device posts from) and a
# time window, show every face access_logs actually recognized
# there during that window — the "who was at this scene, and when"
# view a security investigation needs. Built entirely from existing
# access_logs rows; no new table, consistent with this codebase's
# no-foreign-key, free-text-matching style (a location is just
# whatever string a camera's own `location` field holds).


def _row_to_dict(row):

    return dict(row) if row is not None else None


def _resolve_person_name(cursor, person_type, person_identifier):

    if not person_identifier:

        return None

    if person_type == "STUDENT":

        cursor.execute(
            "SELECT full_name FROM students WHERE student_id = ?",
            (person_identifier,)
        )

    elif person_type == "TARGET":

        cursor.execute(
            "SELECT full_name FROM watchlist_targets WHERE target_id = ?",
            (person_identifier,)
        )

    else:

        return None

    row = cursor.fetchone()

    return row["full_name"] if row else None


def list_locations():

    # Every distinct location a sighting has ever been logged
    # against — populates the scene tool's location picker without
    # requiring every location to also have a registered camera row
    # (some access_logs entries predate the camera registry).

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT DISTINCT entrance FROM access_logs
        WHERE entrance IS NOT NULL
        ORDER BY entrance
    """)

    locations = [row[0] for row in cursor.fetchall()]

    connection.close()

    return locations


def query_scene(location=None, start_time=None, end_time=None):

    # Datetime-local inputs arrive as "YYYY-MM-DDTHH:MM"; access_logs
    # timestamps are SQLite's own "YYYY-MM-DD HH:MM:SS" — normalize
    # so string comparison against the stored value still works.

    if start_time:

        start_time = start_time.replace("T", " ")

    if end_time:

        end_time = end_time.replace("T", " ")

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    query = "SELECT * FROM access_logs WHERE 1=1"
    params = []

    if location:

        query += " AND entrance = ?"
        params.append(location)

    if start_time:

        query += " AND timestamp >= ?"
        params.append(start_time)

    if end_time:

        query += " AND timestamp <= ?"
        params.append(end_time)

    query += " ORDER BY timestamp ASC"

    cursor.execute(query, params)

    rows = cursor.fetchall()

    sightings = []
    people_by_key = {}

    for row in rows:

        sighting = _row_to_dict(row)

        full_name = _resolve_person_name(
            cursor,
            sighting["person_type"],
            sighting["person_identifier"]
        )

        sighting["full_name"] = full_name

        sightings.append(sighting)

        key = (sighting["person_type"], sighting["person_identifier"])

        if key not in people_by_key:

            people_by_key[key] = {
                "person_type": sighting["person_type"],
                "person_identifier": sighting["person_identifier"],
                "full_name": full_name,
                "first_seen": sighting["timestamp"],
                "last_seen": sighting["timestamp"],
                "sighting_count": 0
            }

        people_by_key[key]["last_seen"] = sighting["timestamp"]
        people_by_key[key]["sighting_count"] += 1

    connection.close()

    return {
        "location": location,
        "start_time": start_time,
        "end_time": end_time,
        "people": list(people_by_key.values()),
        "sightings": sightings
    }
