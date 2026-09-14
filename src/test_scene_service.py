import os
import sqlite3
import tempfile


def _create_schema(path):

    connection = sqlite3.connect(path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            admission_number TEXT UNIQUE NOT NULL
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
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


def _insert_log(db_path, person_type, person_identifier, entrance, timestamp, decision="VERIFIED"):

    connection = sqlite3.connect(db_path)
    connection.execute("""
        INSERT INTO access_logs
            (person_type, person_identifier, entrance, decision, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (person_type, person_identifier, entrance, decision, timestamp))
    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing scene_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    connection = sqlite3.connect(temp_db_path)
    connection.execute(
        "INSERT INTO students (student_id, full_name, admission_number) "
        "VALUES ('STU-1', 'Alice Wanjiru', 'AD001')"
    )
    connection.execute(
        "INSERT INTO watchlist_targets (target_id, full_name) "
        "VALUES ('TGT-1', 'Person Of Interest')"
    )
    connection.commit()
    connection.close()

    # A scene: two people at the Library Entrance within the window,
    # one of them seen twice; a third sighting at a different
    # location, and a fourth outside the time window — neither should
    # show up in the Library Entrance / that-hour query below.
    _insert_log(temp_db_path, "STUDENT", "STU-1", "Library Entrance", "2026-09-14 09:00:00")
    _insert_log(temp_db_path, "TARGET", "TGT-1", "Library Entrance", "2026-09-14 09:05:00", decision="TARGET_ALERT")
    _insert_log(temp_db_path, "STUDENT", "STU-1", "Library Entrance", "2026-09-14 09:10:00")
    _insert_log(temp_db_path, "GUEST", "AG-1", "Main Gate", "2026-09-14 09:07:00", decision="AG_VALID")
    _insert_log(temp_db_path, "STUDENT", "STU-1", "Library Entrance", "2026-09-14 11:30:00")

    from src.services import scene_service

    # ------------------------------------------------------------
    # LOCATIONS
    # ------------------------------------------------------------

    locations = scene_service.list_locations()
    assert locations == ["Library Entrance", "Main Gate"]
    print("Distinct locations ->", locations)

    # ------------------------------------------------------------
    # QUERY — a location + time window
    # ------------------------------------------------------------

    scene = scene_service.query_scene(
        location="Library Entrance",
        start_time="2026-09-14 08:00:00",
        end_time="2026-09-14 10:00:00"
    )

    assert scene["location"] == "Library Entrance"
    assert len(scene["sightings"]) == 3
    assert all(s["entrance"] == "Library Entrance" for s in scene["sightings"])
    print(f"Scene sightings in window: {len(scene['sightings'])}")

    people_by_id = {p["person_identifier"]: p for p in scene["people"]}
    assert set(people_by_id.keys()) == {"STU-1", "TGT-1"}

    student_summary = people_by_id["STU-1"]
    assert student_summary["full_name"] == "Alice Wanjiru"
    assert student_summary["sighting_count"] == 2
    assert student_summary["first_seen"] == "2026-09-14 09:00:00"
    assert student_summary["last_seen"] == "2026-09-14 09:10:00"

    target_summary = people_by_id["TGT-1"]
    assert target_summary["full_name"] == "Person Of Interest"
    assert target_summary["sighting_count"] == 1

    print("Scene resolves names and per-person first/last seen + counts ->", scene["people"])

    # The 11:30 Library sighting is outside the window and the AG-1
    # sighting is at a different location — neither leaked in.
    assert not any(
        s["timestamp"] == "2026-09-14 11:30:00" for s in scene["sightings"]
    )
    assert not any(s["person_identifier"] == "AG-1" for s in scene["sightings"])
    print("Out-of-window and out-of-location sightings correctly excluded")

    # ------------------------------------------------------------
    # QUERY — no location filter, full window -> everything
    # ------------------------------------------------------------

    everything = scene_service.query_scene(
        start_time="2026-09-14 00:00:00",
        end_time="2026-09-14 23:59:59"
    )
    assert len(everything["sightings"]) == 5
    print("Location-less query returns every sighting in the window")

    # ------------------------------------------------------------
    # QUERY — datetime-local "T" separator is normalized
    # ------------------------------------------------------------

    normalized = scene_service.query_scene(
        location="Library Entrance",
        start_time="2026-09-14T08:00",
        end_time="2026-09-14T10:00"
    )
    assert len(normalized["sightings"]) == 3
    print("datetime-local 'T'-separated input is normalized and matches correctly")

    # ------------------------------------------------------------
    # CO-OCCURRENCE — who else was seen nearby in time
    # ------------------------------------------------------------
    #
    # STU-1 @ 09:00 and 09:10 bracket TGT-1 @ 09:05 exactly 5 minutes
    # (300s) on each side — the default window's own boundary, so
    # both directions must count as co-occurring, not just one.

    default_window = scene_service.query_scene(
        location="Library Entrance",
        start_time="2026-09-14 08:00:00",
        end_time="2026-09-14 10:00:00"
    )
    assert default_window["co_occurrence_minutes"] == 5

    people_by_id = {p["person_identifier"]: p for p in default_window["people"]}

    student_partners = people_by_id["STU-1"]["co_occurring"]
    assert len(student_partners) == 1
    assert student_partners[0]["person_identifier"] == "TGT-1"
    assert student_partners[0]["full_name"] == "Person Of Interest"
    assert student_partners[0]["closest_gap_seconds"] == 300

    target_partners = people_by_id["TGT-1"]["co_occurring"]
    assert len(target_partners) == 1
    assert target_partners[0]["person_identifier"] == "STU-1"
    assert target_partners[0]["closest_gap_seconds"] == 300

    print("Co-occurrence links STU-1 <-> TGT-1 at the 5-minute boundary, both directions")

    # A narrower window (4 minutes) excludes that same 5-minute gap.
    narrow_window = scene_service.query_scene(
        location="Library Entrance",
        start_time="2026-09-14 08:00:00",
        end_time="2026-09-14 10:00:00",
        co_occurrence_minutes=4
    )
    narrow_people_by_id = {
        p["person_identifier"]: p for p in narrow_window["people"]
    }
    assert narrow_people_by_id["STU-1"]["co_occurring"] == []
    assert narrow_people_by_id["TGT-1"]["co_occurring"] == []
    print("A narrower co-occurrence window correctly excludes a 5-minute-apart pair")

    import shutil
    shutil.rmtree(temp_dir)

    print("\nscene_service smoke test passed.")
