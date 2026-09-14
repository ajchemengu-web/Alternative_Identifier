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
            severity TEXT NOT NULL DEFAULT 'MEDIUM',
            assigned_to TEXT,
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

    connection.execute("""
        CREATE TABLE IF NOT EXISTS investigation_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            linked_by TEXT,
            linked_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS investigation_unknowns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            unknown_id TEXT NOT NULL,
            linked_by TEXT,
            linked_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
        CREATE TABLE IF NOT EXISTS unknown_persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unknown_id TEXT UNIQUE NOT NULL,
            image_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
            detected_at DATETIME DEFAULT CURRENT_TIMESTAMP
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

    connection = sqlite3.connect(temp_db_path)
    connection.execute(
        "INSERT INTO watchlist_targets (target_id, full_name) "
        "VALUES ('TGT-1', 'Person Of Interest')"
    )
    connection.execute(
        "INSERT INTO watchlist_targets (target_id, full_name) "
        "VALUES ('TGT-2', 'Another Person')"
    )
    connection.execute(
        "INSERT INTO unknown_persons (unknown_id, image_path) "
        "VALUES ('UNK-1', '/data/unknowns/unk1.jpg')"
    )
    connection.commit()
    connection.close()

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
    assert case["severity"] == "MEDIUM"
    assert case["assigned_to"] is None
    assert case["notes"] == []
    # The primary target_id shows up in linked_targets too, resolved.
    assert len(case["linked_targets"]) == 1
    assert case["linked_targets"][0]["target_id"] == "TGT-1"
    assert case["linked_targets"][0]["full_name"] == "Person Of Interest"
    assert case["linked_unknowns"] == []
    print("Created case ->", case)

    untargeted_case = investigation_service.create_case(
        title="Unrelated incident, no target link",
        opened_by="original1"
    )
    assert untargeted_case["target_id"] is None
    assert untargeted_case["linked_targets"] == []
    print("Created a case with no linked target ->", untargeted_case)

    high_severity_case = investigation_service.create_case(
        title="Break-in at Library Entrance",
        severity="critical",
        assigned_to="security1",
        opened_by="original1"
    )
    assert high_severity_case["severity"] == "CRITICAL"
    assert high_severity_case["assigned_to"] == "security1"
    print("Created case with explicit severity/assignee ->", {
        k: high_severity_case[k] for k in ("severity", "assigned_to")
    })

    try:
        investigation_service.create_case(
            title="Bad severity", severity="APOCALYPTIC"
        )
        raise AssertionError("Expected ValueError for an invalid severity")
    except ValueError as error:
        print("Invalid severity rejected as expected:", error)

    # ------------------------------------------------------------
    # UPDATE — title/description/severity/assigned_to
    # ------------------------------------------------------------

    updated_fields = investigation_service.update_case(
        case["case_id"], severity="high", assigned_to="original1"
    )
    assert updated_fields["severity"] == "HIGH"
    assert updated_fields["assigned_to"] == "original1"
    print("Updated case severity/assignee ->", {
        k: updated_fields[k] for k in ("severity", "assigned_to")
    })

    try:
        investigation_service.update_case("CASE-NOPE", severity="LOW")
        raise AssertionError("Expected ValueError for an unknown case_id")
    except ValueError as error:
        print("Updating a non-existent case raised, as expected:", error)

    try:
        investigation_service.update_case(case["case_id"])
        raise AssertionError("Expected ValueError when no fields supplied")
    except ValueError as error:
        print("No-op update rejected as expected:", error)

    # ------------------------------------------------------------
    # LINK / UNLINK TARGETS — beyond the single primary target_id
    # ------------------------------------------------------------

    linked = investigation_service.link_target(
        case["case_id"], "TGT-2", linked_by="security1"
    )
    assert len(linked["linked_targets"]) == 2
    linked_ids = {t["target_id"] for t in linked["linked_targets"]}
    assert linked_ids == {"TGT-1", "TGT-2"}
    print("Linked a second target to the case ->", linked["linked_targets"])

    # Idempotent — linking the same target again doesn't duplicate it.
    relinked = investigation_service.link_target(
        case["case_id"], "TGT-2", linked_by="security1"
    )
    assert len(relinked["linked_targets"]) == 2
    print("Re-linking the same target is idempotent")

    try:
        investigation_service.link_target(case["case_id"], "TGT-MISSING")
        raise AssertionError("Expected ValueError for an unknown target_id")
    except ValueError as error:
        print("Linking an unknown target rejected as expected:", error)

    unlinked = investigation_service.unlink_target(case["case_id"], "TGT-2")
    assert unlinked is True
    after_unlink = investigation_service.get_case(case["case_id"])
    assert len(after_unlink["linked_targets"]) == 1
    assert after_unlink["linked_targets"][0]["target_id"] == "TGT-1"
    print("Unlinked the second target, primary target_id link remains")

    assert investigation_service.unlink_target(case["case_id"], "TGT-2") is False
    print("Unlinking an already-unlinked target returns False, as expected")

    # Unlinking the *primary* target_id (not a investigation_targets
    # row) has to work the same way from the caller's point of view —
    # otherwise it would silently no-op since there's no join row to
    # delete for it.
    unlinked_primary = investigation_service.unlink_target(case["case_id"], "TGT-1")
    assert unlinked_primary is True
    after_primary_unlink = investigation_service.get_case(case["case_id"])
    assert after_primary_unlink["target_id"] is None
    assert after_primary_unlink["linked_targets"] == []
    print("Unlinking the primary target clears target_id too, not just a join row")

    # ------------------------------------------------------------
    # LINK / UNLINK UNKNOWN_PERSONS SIGHTINGS
    # ------------------------------------------------------------

    with_unknown = investigation_service.link_unknown(
        untargeted_case["case_id"], "UNK-1", linked_by="original1"
    )
    assert len(with_unknown["linked_unknowns"]) == 1
    assert with_unknown["linked_unknowns"][0]["unknown_id"] == "UNK-1"
    assert with_unknown["linked_unknowns"][0]["status"] == "PENDING_REVIEW"
    print("Linked an unknown_persons sighting to the case ->", with_unknown["linked_unknowns"])

    try:
        investigation_service.link_unknown(untargeted_case["case_id"], "UNK-MISSING")
        raise AssertionError("Expected ValueError for an unknown unknown_id")
    except ValueError as error:
        print("Linking an unknown unknown_id rejected as expected:", error)

    unlinked_unknown = investigation_service.unlink_unknown(
        untargeted_case["case_id"], "UNK-1"
    )
    assert unlinked_unknown is True
    after_unknown_unlink = investigation_service.get_case(untargeted_case["case_id"])
    assert after_unknown_unlink["linked_unknowns"] == []
    print("Unlinked the unknown_persons sighting")

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
    assert len(all_cases) == 3
    print(f"All cases: {len(all_cases)}")

    open_cases = investigation_service.list_cases(status="open")
    assert len(open_cases) == 3
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

    assert len(investigation_service.list_cases(status="open")) == 2
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
