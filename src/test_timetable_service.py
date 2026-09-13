import os
import sqlite3
import tempfile


def _create_schema(path):

    connection = sqlite3.connect(path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS timetable_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course TEXT NOT NULL,
            year INTEGER NOT NULL,
            department TEXT,
            semester INTEGER,
            day_of_week TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            unit_name TEXT NOT NULL,
            facilitator TEXT NOT NULL,
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

    from src.services import timetable_service

    # ------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------

    entry = timetable_service.create_entry(
        course="BSc Computer Science",
        year=2,
        day_of_week="monday",
        start_time="09:00",
        end_time="11:00",
        unit_name="Data Structures",
        facilitator="Dr. Otieno",
        venue="Hall A",
        created_by="timetabling_admin",
        department="School of Computing",
        semester=1
    )

    assert entry["day_of_week"] == "MONDAY"
    assert entry["status"] == "ON"
    assert entry["department"] == "School of Computing"
    assert entry["semester"] == 1
    print("Created entry ->", entry)

    timetable_service.create_entry(
        course="BSc Computer Science",
        year=2,
        day_of_week="WEDNESDAY",
        start_time="14:00",
        end_time="16:00",
        unit_name="Databases",
        facilitator="Dr. Wanjiru",
        venue="Hall B",
        created_by="timetabling_admin",
        semester=2
    )

    timetable_service.create_entry(
        course="BSc Computer Science",
        year=1,
        day_of_week="TUESDAY",
        start_time="08:00",
        end_time="10:00",
        unit_name="Intro to Programming",
        facilitator="Dr. Kamau",
        venue="Hall C",
        created_by="timetabling_admin"
    )

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
    assert len(department_entries) == 1
    assert department_entries[0]["unit_name"] == "Data Structures"
    print(f"Department-filtered entries: {len(department_entries)}")

    no_department_match = timetable_service.list_entries(
        department="School of Business"
    )
    assert len(no_department_match) == 0
    print("Non-matching department filter returns no entries, as expected")

    semester_1_entries = timetable_service.list_entries(semester=1)
    assert len(semester_1_entries) == 1
    assert semester_1_entries[0]["unit_name"] == "Data Structures"
    print(f"Semester 1 entries: {len(semester_1_entries)}")

    semester_2_entries = timetable_service.list_entries(semester=2)
    assert len(semester_2_entries) == 1
    assert semester_2_entries[0]["unit_name"] == "Databases"
    print(f"Semester 2 entries: {len(semester_2_entries)}")

    no_semester_match = timetable_service.list_entries(semester=99)
    assert len(no_semester_match) == 0
    print("Non-matching semester filter returns no entries, as expected")

    facilitator_entries = timetable_service.list_entries(
        facilitator="Dr. Kamau"
    )
    assert len(facilitator_entries) == 1
    assert facilitator_entries[0]["unit_name"] == "Intro to Programming"
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
            course="BSc Computer Science",
            year=1,
            day_of_week="NOTADAY",
            start_time="08:00",
            end_time="09:00",
            unit_name="X",
            facilitator="Y",
            venue="Z"
        )
        raise AssertionError("Expected ValueError for invalid day_of_week")
    except ValueError as error:
        print("Invalid day_of_week rejected as expected:", error)

    import shutil
    shutil.rmtree(temp_dir)

    print("\ntimetable_service smoke test passed.")
