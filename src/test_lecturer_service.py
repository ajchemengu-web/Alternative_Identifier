import os
import sqlite3
import tempfile


def _create_schema(path):

    connection = sqlite3.connect(path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS lecturers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lecturer_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            department TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing lecturer_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    from src.services import lecturer_service

    # ------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------

    lecturer = lecturer_service.create_lecturer(
        lecturer_id="L1",
        full_name="Dr. Otieno",
        department="School of Computing"
    )

    assert lecturer["lecturer_id"] == "L1"
    assert lecturer["full_name"] == "Dr. Otieno"
    print("Created lecturer ->", lecturer)

    lecturer_service.create_lecturer(
        lecturer_id="L2",
        full_name="Dr. Mwangi",
        department="School of Business"
    )

    try:
        lecturer_service.create_lecturer(
            lecturer_id="L1",
            full_name="Duplicate Otieno"
        )
        raise AssertionError("Expected ValueError for duplicate lecturer_id")
    except ValueError as error:
        print("Duplicate lecturer_id rejected as expected:", error)

    # ------------------------------------------------------------
    # LIST / FILTER
    # ------------------------------------------------------------

    all_lecturers = lecturer_service.list_lecturers()
    assert len(all_lecturers) == 2
    print(f"All lecturers: {len(all_lecturers)}")

    computing_only = lecturer_service.list_lecturers(
        department="School of Computing"
    )
    assert len(computing_only) == 1
    assert computing_only[0]["lecturer_id"] == "L1"
    print(f"Department-filtered lecturers: {len(computing_only)}")

    no_match = lecturer_service.list_lecturers(department="School of Law")
    assert no_match == []
    print("Non-matching department filter returns empty, as expected")

    import shutil
    shutil.rmtree(temp_dir)

    print("\nlecturer_service smoke test passed.")
