import os
import sqlite3
import tempfile


def _create_schema(path):

    connection = sqlite3.connect(path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS investigations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            target_id TEXT,
            status TEXT NOT NULL DEFAULT 'OPEN',
            opened_by TEXT,
            opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            closed_by TEXT,
            closed_at DATETIME
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS investigation_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            author TEXT,
            note TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


if __name__ == "__main__":

    print("Testing investigation_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_smarthostel.db")

    _create_schema(temp_db_path)

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    from src.services import investigation_service

    # ------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------

    case = investigation_service.create_case(
        title="Repeated after-hours sighting at Side Gate",
        description="Same unidentified face flagged three nights running.",
        target_id="TGT-1",
        opened_by="security1"
    )

    assert case["case_id"].startswith("CASE-")
    assert case["status"] == "OPEN"
    assert case["target_id"] == "TGT-1"
    assert case["notes"] == []
    print("Created case ->", case)

    untargeted_case = investigation_service.create_case(
        title="Unrelated incident, no target link",
        opened_by="original1"
    )
    assert untargeted_case["target_id"] is None
    print("Created a case with no linked target ->", untargeted_case)

    # ------------------------------------------------------------
    # NOTES — append-only timeline
    # ------------------------------------------------------------

    updated = investigation_service.add_note(
        case["case_id"],
        "Reviewed camera footage from all three nights.",
        author="security1"
    )
    assert len(updated["notes"]) == 1
    assert updated["notes"][0]["note"] == (
        "Reviewed camera footage from all three nights."
    )
    assert updated["notes"][0]["author"] == "security1"
    print("Added first note ->", updated["notes"])

    investigation_service.add_note(
        case["case_id"], "Escalated to Original Admin.", author="security1"
    )
    with_two_notes = investigation_service.get_case(case["case_id"])
    assert len(with_two_notes["notes"]) == 2
    # Oldest first — a readable timeline, not newest-first.
    assert with_two_notes["notes"][0]["note"].startswith("Reviewed")
    assert with_two_notes["notes"][1]["note"].startswith("Escalated")
    print(f"Case now has {len(with_two_notes['notes'])} notes, oldest first")

    try:
        investigation_service.add_note("CASE-NOPE", "orphan note")
        raise AssertionError("Expected ValueError for an unknown case_id")
    except ValueError as error:
        print("Adding a note to a non-existent case raised, as expected:", error)

    # ------------------------------------------------------------
    # LIST / FILTER
    # ------------------------------------------------------------

    all_cases = investigation_service.list_cases()
    assert len(all_cases) == 2
    print(f"All cases: {len(all_cases)}")

    open_cases = investigation_service.list_cases(status="open")
    assert len(open_cases) == 2
    print(f"Open cases: {len(open_cases)}")

    # ------------------------------------------------------------
    # CLOSE / REOPEN
    # ------------------------------------------------------------

    closed = investigation_service.close_case(case["case_id"], "security1")
    assert closed is True

    closed_case = investigation_service.get_case(case["case_id"])
    assert closed_case["status"] == "CLOSED"
    assert closed_case["closed_by"] == "security1"
    assert closed_case["closed_at"] is not None
    print("Case closed ->", {
        k: closed_case[k] for k in ("case_id", "status", "closed_by", "closed_at")
    })

    assert len(investigation_service.list_cases(status="open")) == 1
    print("Closed case excluded from the open filter")

    missing_close = investigation_service.close_case("CASE-NOPE", "x")
    assert missing_close is False
    print("Closing a non-existent case returns False, as expected")

    reopened = investigation_service.reopen_case(case["case_id"])
    assert reopened is True

    reopened_case = investigation_service.get_case(case["case_id"])
    assert reopened_case["status"] == "OPEN"
    assert reopened_case["closed_by"] is None
    assert reopened_case["closed_at"] is None
    print("Case reopened, closed_by/closed_at cleared ->", reopened_case)

    # ------------------------------------------------------------
    # GET — unknown case_id
    # ------------------------------------------------------------

    assert investigation_service.get_case("CASE-NOPE") is None
    print("Getting a non-existent case returns None, as expected")

    import shutil
    shutil.rmtree(temp_dir)

    print("\ninvestigation_service smoke test passed.")
