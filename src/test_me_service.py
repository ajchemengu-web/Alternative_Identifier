import os
import sqlite3
import tempfile


def _create_schema(path):

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
            temp_expires_at DATETIME,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

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

    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing me_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    connection = sqlite3.connect(temp_db_path)

    connection.execute("""
        INSERT INTO students (
            student_id, full_name, admission_number,
            hostel, room, department, course, year, embedding_file
        )
        VALUES ('S1', 'Alice Wanjiru', 'AD001', 'N/A', 'N/A',
                'School of Computing', 'BSc Computer Science', 2, 'na.npy')
    """)

    connection.execute("""
        INSERT INTO users (
            username, password_hash, email, role, linked_person_id
        )
        VALUES ('alice.student', 'hash', 'alice@example.com', 'STUDENT', 'S1')
    """)

    connection.execute("""
        INSERT INTO users (
            username, password_hash, email, role, linked_person_id
        )
        VALUES ('orphan.student', 'hash', 'orphan@example.com', 'STUDENT', 'S99')
    """)

    connection.execute("""
        INSERT INTO users (
            username, password_hash, email, role
        )
        VALUES ('bob.guard', 'hash', 'bob@example.com', 'GUARD')
    """)

    connection.commit()
    connection.close()

    from src.services import me_service

    # ------------------------------------------------------------
    # LINKED STUDENT
    # ------------------------------------------------------------

    profile = me_service.get_my_student_profile("alice.student")
    assert profile is not None
    assert profile["student_id"] == "S1"
    assert profile["course"] == "BSc Computer Science"
    assert profile["year"] == 2
    print("Linked student profile resolved ->", profile)

    # ------------------------------------------------------------
    # LINKED TO A NON-EXISTENT STUDENT RECORD
    # ------------------------------------------------------------

    orphan_profile = me_service.get_my_student_profile("orphan.student")
    assert orphan_profile is None
    print("Orphaned linked_person_id resolves to None, as expected")

    # ------------------------------------------------------------
    # USER WITH NO linked_person_id AT ALL
    # ------------------------------------------------------------

    guard_profile = me_service.get_my_student_profile("bob.guard")
    assert guard_profile is None
    print("User with no linked_person_id resolves to None, as expected")

    # ------------------------------------------------------------
    # UNKNOWN USERNAME
    # ------------------------------------------------------------

    missing_profile = me_service.get_my_student_profile("nobody")
    assert missing_profile is None
    print("Unknown username resolves to None, as expected")

    import shutil
    shutil.rmtree(temp_dir)

    print("\nme_service smoke test passed.")
