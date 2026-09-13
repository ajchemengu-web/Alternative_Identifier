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

    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing unit_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    from src.services import unit_service

    # ------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------

    unit = unit_service.create_unit(
        unit_code="SCO 104",
        unit_name="Object Oriented Programming I",
        course="BSc Computer Science",
        year=1,
        semester=1,
        department="School of Computing",
        created_by="timetabling_admin"
    )

    assert unit["unit_code"] == "SCO 104"
    assert unit["lecturer_id"] is None
    print("Created unit ->", unit)

    unit_service.create_unit(
        unit_code="SCO 106",
        unit_name="Software Engineering",
        course="BSc Computer Science",
        year=1,
        semester=1
    )

    try:
        unit_service.create_unit(
            unit_code="SCO 104",
            unit_name="Duplicate code",
            course="BSc Computer Science",
            year=1,
            semester=1
        )
        raise AssertionError("Expected ValueError for duplicate unit_code")
    except ValueError as error:
        print("Duplicate unit_code rejected as expected:", error)

    # ------------------------------------------------------------
    # LIST / FILTER
    # ------------------------------------------------------------

    all_units = unit_service.list_units()
    assert len(all_units) == 2
    print(f"All units: {len(all_units)}")

    unclaimed = unit_service.list_units(unclaimed=True)
    assert len(unclaimed) == 2
    print(f"Unclaimed units: {len(unclaimed)}")

    # ------------------------------------------------------------
    # CLAIM
    # ------------------------------------------------------------

    claimed = unit_service.claim_unit(unit["id"], "L1")
    assert claimed["lecturer_id"] == "L1"
    print("Lecturer L1 claimed the unit ->", claimed)

    # Claiming again (same lecturer) is idempotent, not an error.
    reclaimed = unit_service.claim_unit(unit["id"], "L1")
    assert reclaimed["lecturer_id"] == "L1"
    print("Re-claiming your own unit is a no-op, as expected")

    try:
        unit_service.claim_unit(unit["id"], "L2")
        raise AssertionError("Expected ValueError for claiming someone else's unit")
    except ValueError as error:
        print("Claiming another lecturer's unit is rejected, as expected:", error)

    still_unclaimed = unit_service.list_units(unclaimed=True)
    assert len(still_unclaimed) == 1
    print(f"Unclaimed units after one claim: {len(still_unclaimed)}")

    mine = unit_service.list_units(lecturer_id="L1")
    assert len(mine) == 1
    assert mine[0]["unit_code"] == "SCO 104"
    print("Lecturer-filtered units ->", mine)

    # ------------------------------------------------------------
    # UNCLAIM
    # ------------------------------------------------------------

    try:
        unit_service.unclaim_unit(unit["id"], "L2")
        raise AssertionError("Expected ValueError for unclaiming someone else's unit")
    except ValueError as error:
        print("Unclaiming a unit you don't hold is rejected, as expected:", error)

    released = unit_service.unclaim_unit(unit["id"], "L1")
    assert released["lecturer_id"] is None
    print("Lecturer released their claim ->", released)

    # ------------------------------------------------------------
    # ADMIN OVERRIDE
    # ------------------------------------------------------------

    reassigned = unit_service.set_unit_lecturer(unit["id"], "L3")
    assert reassigned["lecturer_id"] == "L3"
    print("Admin directly assigned the unit to L3 ->", reassigned)

    cleared = unit_service.set_unit_lecturer(unit["id"], None)
    assert cleared["lecturer_id"] is None
    print("Admin cleared the assignment back to unclaimed ->", cleared)

    try:
        unit_service.set_unit_lecturer(9999, "L1")
        raise AssertionError("Expected ValueError for a non-existent unit")
    except ValueError as error:
        print("Reassigning a non-existent unit is rejected, as expected:", error)

    import shutil
    shutil.rmtree(temp_dir)

    print("\nunit_service smoke test passed.")
