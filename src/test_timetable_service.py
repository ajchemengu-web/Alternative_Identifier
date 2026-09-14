import os
import sqlite3
import tempfile


def _create_schema(path):

    connection = sqlite3.connect(path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_code TEXT UNIQUE NOT NULL,
            unit_name TEXT NOT NULL,
            department TEXT,
            course TEXT NOT NULL,
            year INTEGER NOT NULL,
            semester INTEGER NOT NULL,
            lecturer_id TEXT,
            created_by TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS lecturers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lecturer_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            department TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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

    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing timetable_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    from src.services import unit_service, timetable_service

    connection = sqlite3.connect(temp_db_path)
    connection.execute("""
        INSERT INTO lecturers (lecturer_id, full_name)
        VALUES ('L1', 'Dr. Otieno')
    """)
    connection.commit()
    connection.close()

    # ------------------------------------------------------------
    # SET UP UNITS: one claimed (Data Structures, sem 1), one
    # unclaimed (Databases, sem 2), one in a different year
    # (Intro to Programming, year 1, unclaimed)
    # ------------------------------------------------------------

    data_structures = unit_service.create_unit(
        unit_code="SCO 104",
        unit_name="Data Structures",
        course="BSc Computer Science",
        year=2,
        semester=1,
        department="School of Computing",
        created_by="timetabling_admin"
    )
    unit_service.claim_unit(data_structures["id"], "L1")

    databases = unit_service.create_unit(
        unit_code="SCO 106",
        unit_name="Databases",
        course="BSc Computer Science",
        year=2,
        semester=2,
        department="School of Computing",
        created_by="timetabling_admin"
    )

    intro_to_programming = unit_service.create_unit(
        unit_code="SCO 100",
        unit_name="Intro to Programming",
        course="BSc Computer Science",
        year=1,
        semester=1,
        created_by="timetabling_admin"
    )

    # ------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------

    entry = timetable_service.create_entry(
        unit_id=data_structures["id"],
        day_of_week="monday",
        start_time="09:00",
        end_time="11:00",
        venue="Hall A",
        created_by="timetabling_admin"
    )

    assert entry["day_of_week"] == "MONDAY"
    assert entry["status"] == "ON"
    assert entry["department"] == "School of Computing"
    assert entry["semester"] == 1
    assert entry["unit_name"] == "Data Structures"
    assert entry["unit_code"] == "SCO 104"
    assert entry["lecturer_id"] == "L1"
    assert entry["facilitator"] == "Dr. Otieno"
    print("Created entry (unit already claimed) ->", entry)

    timetable_service.create_entry(
        unit_id=databases["id"],
        day_of_week="WEDNESDAY",
        start_time="14:00",
        end_time="16:00",
        venue="Hall B",
        created_by="timetabling_admin"
    )

    unclaimed_entry = timetable_service.create_entry(
        unit_id=intro_to_programming["id"],
        day_of_week="TUESDAY",
        start_time="08:00",
        end_time="10:00",
        venue="Hall C",
        created_by="timetabling_admin"
    )

    assert unclaimed_entry["lecturer_id"] is None
    assert unclaimed_entry["facilitator"] is None
    print("An entry for a still-unclaimed unit has no facilitator yet ->", unclaimed_entry)

    try:
        timetable_service.create_entry(
            unit_id=9999,
            day_of_week="MONDAY",
            start_time="08:00",
            end_time="09:00",
            venue="Z"
        )
        raise AssertionError("Expected ValueError for a non-existent unit_id")
    except ValueError as error:
        print("Non-existent unit_id rejected as expected:", error)

    # ------------------------------------------------------------
    # LIST / FILTER
    # ------------------------------------------------------------

    all_entries = timetable_service.list_entries()
    assert len(all_entries) == 3
    print(f"All entries: {len(all_entries)}")

    year_2_entries = timetable_service.list_entries(
        course="BSc Computer Science",
        year=2
    )
    assert len(year_2_entries) == 2
    print(f"Year 2 entries: {len(year_2_entries)}")

    year_1_entries = timetable_service.list_entries(
        course="BSc Computer Science",
        year=1
    )
    assert len(year_1_entries) == 1
    print(f"Year 1 entries: {len(year_1_entries)}")

    department_entries = timetable_service.list_entries(
        department="School of Computing"
    )
    assert len(department_entries) == 2
    print(f"Department-filtered entries: {len(department_entries)}")

    no_department_match = timetable_service.list_entries(
        department="School of Business"
    )
    assert len(no_department_match) == 0
    print("Non-matching department filter returns no entries, as expected")

    semester_1_entries = timetable_service.list_entries(semester=1)
    assert len(semester_1_entries) == 2
    print(f"Semester 1 entries: {len(semester_1_entries)}")

    semester_2_entries = timetable_service.list_entries(semester=2)
    assert len(semester_2_entries) == 1
    assert semester_2_entries[0]["unit_name"] == "Databases"
    print(f"Semester 2 entries: {len(semester_2_entries)}")

    lecturer_entries = timetable_service.list_entries(lecturer_id="L1")
    assert len(lecturer_entries) == 1
    assert lecturer_entries[0]["unit_name"] == "Data Structures"
    print(f"Lecturer L1's entries: {len(lecturer_entries)}")

    no_lecturer_match = timetable_service.list_entries(lecturer_id="L99")
    assert len(no_lecturer_match) == 0
    print("Non-matching lecturer_id filter returns no entries, as expected")

    unit_filtered = timetable_service.list_entries(unit_id=databases["id"])
    assert len(unit_filtered) == 1
    assert unit_filtered[0]["unit_name"] == "Databases"
    print(f"Unit-filtered entries: {len(unit_filtered)}")

    facilitator_entries = timetable_service.list_entries(
        facilitator="Dr. Otieno"
    )
    assert len(facilitator_entries) == 1
    assert facilitator_entries[0]["unit_name"] == "Data Structures"
    print(f"Facilitator-filtered entries: {len(facilitator_entries)}")

    no_facilitator_match = timetable_service.list_entries(
        facilitator="Dr. Nobody"
    )
    assert len(no_facilitator_match) == 0
    print("Non-matching facilitator filter returns no entries, as expected")

    # ------------------------------------------------------------
    # UPDATE STATUS
    # ------------------------------------------------------------

    target_id = year_1_entries[0]["id"]

    updated = timetable_service.update_status(target_id, "postponed")
    assert updated is True

    refreshed = timetable_service.list_entries(
        course="BSc Computer Science",
        year=1
    )
    assert refreshed[0]["status"] == "POSTPONED"
    print("Status updated to POSTPONED ->", refreshed[0])

    missing_update = timetable_service.update_status(9999, "ON")
    assert missing_update is False
    print("Updating a non-existent entry returns False, as expected")

    try:
        timetable_service.update_status(target_id, "NOT_A_REAL_STATUS")
        raise AssertionError("Expected ValueError for invalid status")
    except ValueError as error:
        print("Invalid status rejected as expected:", error)

    # ------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------

    deleted = timetable_service.delete_entry(target_id)
    assert deleted is True

    missing_delete = timetable_service.delete_entry(target_id)
    assert missing_delete is False

    assert len(timetable_service.list_entries()) == 2
    print("Delete removed the entry and is idempotent-safe (second delete -> False)")

    try:
        timetable_service.create_entry(
            unit_id=intro_to_programming["id"],
            day_of_week="NOTADAY",
            start_time="08:00",
            end_time="09:00",
            venue="Z"
        )
        raise AssertionError("Expected ValueError for invalid day_of_week")
    except ValueError as error:
        print("Invalid day_of_week rejected as expected:", error)

    import shutil
    shutil.rmtree(temp_dir)

    print("\ntimetable_service smoke test passed.")
