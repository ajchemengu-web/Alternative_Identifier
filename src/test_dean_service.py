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
            admission_number TEXT UNIQUE NOT NULL,
            hostel TEXT NOT NULL,
            room TEXT NOT NULL,
            department TEXT,
            course TEXT,
            year INTEGER,
            embedding_file TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

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


def _insert_student(
    connection,
    student_id,
    full_name,
    admission_number,
    department,
    course,
    year
):

    connection.execute("""
        INSERT INTO students (
            student_id, full_name, admission_number,
            hostel, room, department, course, year, embedding_file
        )
        VALUES (?, ?, ?, 'N/A', 'N/A', ?, ?, ?, 'na.npy')
    """, (
        student_id, full_name, admission_number, department, course, year
    ))


if __name__ == "__main__":

    print("Testing dean_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    raw_connection = sqlite3.connect(temp_db_path)

    _insert_student(
        raw_connection, "S1", "Alice Wanjiru", "AD001",
        "School of Computing", "BSc Computer Science", 2
    )
    _insert_student(
        raw_connection, "S2", "Brian Otieno", "AD002",
        "School of Computing", "BSc Computer Science", 2
    )
    _insert_student(
        raw_connection, "S3", "Carol Njeri", "AD003",
        "School of Computing", "BSc Computer Science", 1
    )
    _insert_student(
        raw_connection, "S4", "Dennis Kamau", "AD004",
        "School of Business", "BCom", 1
    )

    raw_connection.commit()
    raw_connection.close()

    from src.services import unit_service, timetable_service, dean_service

    data_structures = unit_service.create_unit(
        unit_code="SCO 104",
        unit_name="Data Structures",
        course="BSc Computer Science",
        year=2,
        semester=1,
        department="School of Computing",
        created_by="timetabling_admin"
    )

    intro_to_programming = unit_service.create_unit(
        unit_code="SCO 100",
        unit_name="Intro to Programming",
        course="BSc Computer Science",
        year=1,
        semester=1,
        department="School of Computing",
        created_by="timetabling_admin"
    )

    accounting = unit_service.create_unit(
        unit_code="BCM 101",
        unit_name="Accounting",
        course="BCom",
        year=1,
        semester=1,
        department="School of Business",
        created_by="timetabling_admin"
    )

    timetable_service.create_entry(
        unit_id=data_structures["id"],
        day_of_week="MONDAY",
        start_time="09:00",
        end_time="11:00",
        venue="Hall A",
        created_by="timetabling_admin"
    )

    timetable_service.create_entry(
        unit_id=intro_to_programming["id"],
        day_of_week="TUESDAY",
        start_time="08:00",
        end_time="10:00",
        venue="Hall C",
        created_by="timetabling_admin"
    )

    timetable_service.create_entry(
        unit_id=accounting["id"],
        day_of_week="WEDNESDAY",
        start_time="10:00",
        end_time="12:00",
        venue="Hall D",
        created_by="timetabling_admin"
    )

    # ------------------------------------------------------------
    # ROSTER — department scoping
    # ------------------------------------------------------------

    computing_roster = dean_service.get_roster("School of Computing")
    assert len(computing_roster) == 3
    print(f"School of Computing roster: {len(computing_roster)} students")

    business_roster = dean_service.get_roster("School of Business")
    assert len(business_roster) == 1
    assert business_roster[0]["student_id"] == "S4"
    print(f"School of Business roster: {len(business_roster)} student")

    all_roster = dean_service.get_roster()
    assert len(all_roster) == 4
    print(f"Unfiltered roster: {len(all_roster)} students")

    no_match_roster = dean_service.get_roster("School of Law")
    assert no_match_roster == []
    print("Non-matching department roster returns empty, as expected")

    # ------------------------------------------------------------
    # CLASSIFICATION SUMMARY
    # ------------------------------------------------------------

    classification = dean_service.get_classification_summary(
        "School of Computing"
    )
    assert classification == [
        {
            "course": "BSc Computer Science",
            "year": 1,
            "student_count": 1
        },
        {
            "course": "BSc Computer Science",
            "year": 2,
            "student_count": 2
        }
    ]
    print("Classification summary ->", classification)

    # ------------------------------------------------------------
    # SUMMARY — roster + timetable/unit totals
    # ------------------------------------------------------------

    summary = dean_service.get_summary("School of Computing")
    assert summary["department"] == "School of Computing"
    assert summary["total_students"] == 3
    assert summary["total_units"] == 2
    assert summary["total_active_lectures"] == 2
    assert summary["total_timetable_entries"] == 2
    print("Summary ->", summary)

    # Postponing an entry drops it out of total_active_lectures but
    # not out of total_timetable_entries.
    business_entry_id = timetable_service.list_entries(
        department="School of Business"
    )[0]["id"]

    timetable_service.update_status(business_entry_id, "POSTPONED")

    business_summary = dean_service.get_summary("School of Business")
    assert business_summary["total_timetable_entries"] == 1
    assert business_summary["total_active_lectures"] == 0
    print("Postponed entry excluded from active-lecture count ->", business_summary)

    import shutil
    shutil.rmtree(temp_dir)

    print("\ndean_service smoke test passed.")
