import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

from src.services import audit_service


def _create_table(path):

    connection = sqlite3.connect(path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            times INTEGER NOT NULL DEFAULT 1,
            username TEXT NOT NULL,
            role TEXT,
            admin_tier TEXT,
            department TEXT,
            action TEXT NOT NULL,
            subject_id TEXT NOT NULL DEFAULT '',
            params TEXT NOT NULL DEFAULT '{}'
        )
    """)

    connection.commit()
    connection.close()


def _rows(path):

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    rows = connection.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    connection.close()

    return [dict(row) for row in rows]


def _raises(exception, function, *args, **kwargs):

    try:

        function(*args, **kwargs)

    except exception as error:

        return error

    raise AssertionError(f"Expected {exception.__name__}")


if __name__ == "__main__":

    print("Testing audit_service against an isolated temp database...")

    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test.db")

    import src.db as db
    db.DATABASE_PATH = temp_db_path

    # ------------------------------------------------------------
    # READINESS
    # ------------------------------------------------------------

    error = _raises(RuntimeError, audit_service.require_ready)
    assert "upgrade_audit_log_table" in str(error)
    print("Startup check refuses to run when the table is missing")

    _create_table(temp_db_path)
    audit_service.require_ready()
    print("Startup check passes once the table exists")

    # ------------------------------------------------------------
    # RECORDING
    # ------------------------------------------------------------

    admin = {"username": "root", "role": "ADMIN", "admin_tier": "ORIGINAL",
             "department": None}
    dean = {"username": "dean1", "role": "ADMIN", "admin_tier": "DEAN",
            "department": "School of Business"}

    t0 = datetime(2026, 10, 2, 9, 0, 0, tzinfo=timezone.utc)

    audit_service.record_read(admin, "students.list", now=t0)

    rows = _rows(temp_db_path)
    assert len(rows) == 1
    row = rows[0]
    assert (row["username"], row["role"], row["admin_tier"]) == (
        "root", "ADMIN", "ORIGINAL")
    assert row["action"] == "students.list"
    assert row["subject_id"] == "" and row["params"] == "{}"
    assert row["times"] == 1
    assert row["occurred_at"] == "2026-10-02T09:00:00+00:00"
    print("A read records who, what and when ->", row)

    audit_service.record_read(dean, "dean.roster", now=t0)
    assert _rows(temp_db_path)[-1]["department"] == "School of Business"
    print("A Dean's department is recorded with the read")

    # ------------------------------------------------------------
    # COALESCING
    # ------------------------------------------------------------

    count = len(_rows(temp_db_path))

    for seconds in (10, 60, 200):
        audit_service.record_read(
            admin, "students.list", now=t0 + timedelta(seconds=seconds))

    rows = _rows(temp_db_path)
    assert len(rows) == count
    assert rows[0]["times"] == 4
    assert rows[0]["last_seen_at"] == "2026-10-02T09:03:20+00:00"
    assert rows[0]["occurred_at"] == "2026-10-02T09:00:00+00:00"
    print("Repeated identical reads inside the window are one row (times=4)")

    audit_service.record_read(
        admin, "students.list", now=t0 + timedelta(seconds=301))
    rows = _rows(temp_db_path)
    assert len(rows) == count + 1
    print("A read after the window starts a new row — polling can't stretch "
          "one row forever")

    # Continuous polling keeps producing a row per window, not one row.
    for step in range(0, 1300, 5):
        audit_service.record_read(
            admin, "access_logs.list",
            now=t0 + timedelta(seconds=step))
    polled = [r for r in _rows(temp_db_path) if r["action"] == "access_logs.list"]
    assert len(polled) == 5 and sum(r["times"] for r in polled) == 260
    print("A client polling every 5s for ~22 minutes -> 5 rows, 260 reads")

    before = len(_rows(temp_db_path))
    audit_service.record_read(admin, "students.list", params={"department": "A"},
                              now=t0 + timedelta(seconds=302))
    audit_service.record_read(admin, "students.list", params={"department": "B"},
                              now=t0 + timedelta(seconds=303))
    audit_service.record_read(dean, "students.list",
                              now=t0 + timedelta(seconds=304))
    audit_service.record_read(admin, "watchlist.sightings", subject="TGT-1",
                              now=t0 + timedelta(seconds=305))
    audit_service.record_read(admin, "watchlist.sightings", subject="TGT-2",
                              now=t0 + timedelta(seconds=306))
    assert len(_rows(temp_db_path)) == before + 5
    print("Different filters, users or subjects are never merged")

    # ------------------------------------------------------------
    # WHAT GETS STORED FROM THE REQUEST
    # ------------------------------------------------------------

    audit_service.record_read(
        admin, "scene.query", now=t0,
        params={"token": "SECRET", "Password": "x", "authorization": "Bearer y",
                "location": "Main Gate", "empty": "", "none": None,
                "long": "x" * 500})
    stored = _rows(temp_db_path)[-1]["params"]
    assert "SECRET" not in stored and "Bearer" not in stored
    assert "Main Gate" in stored and "empty" not in stored
    assert max(len(v) for v in __import__("json").loads(stored).values()) == 120
    print("Secrets are dropped, values are capped, blanks are skipped")

    audit_service.record_read(
        admin, "scene.query", now=t0 + timedelta(hours=1),
        params={f"k{i:02d}": "v" for i in range(40)})
    assert len(__import__("json").loads(_rows(temp_db_path)[-1]["params"])) == 10
    print("A request can't bloat the log with hundreds of parameters")

    # ------------------------------------------------------------
    # FAIL CLOSED
    # ------------------------------------------------------------

    broken = os.path.join(temp_dir, "broken.db")
    sqlite3.connect(broken).close()
    db.DATABASE_PATH = broken

    _raises(audit_service.AuditUnavailableError,
            audit_service.record_read, admin, "students.list")
    print("If the read can't be recorded, an error is raised (-> read refused)")

    db.DATABASE_PATH = temp_db_path

    # ------------------------------------------------------------
    # LISTING
    # ------------------------------------------------------------

    everything = audit_service.list_entries(limit=500)
    assert everything[0]["id"] > everything[-1]["id"]
    assert isinstance(everything[0]["params"], dict)
    print("Entries come back newest first with params decoded")

    mine = audit_service.list_entries(username="dean1")
    assert mine and {e["username"] for e in mine} == {"dean1"}
    only_action = audit_service.list_entries(action="watchlist.sightings")
    assert {e["action"] for e in only_action} == {"watchlist.sightings"}
    only_subject = audit_service.list_entries(subject="TGT-2")
    assert len(only_subject) == 1 and only_subject[0]["subject_id"] == "TGT-2"
    print("Filter by user, action and subject")

    window = audit_service.list_entries(
        since="2026-10-02T09:05:00", until="2026-10-02T09:10:00", limit=500)
    assert window and all(
        "2026-10-02T09:05:00" <= e["occurred_at"] <= "2026-10-02T09:10:00+00:00"
        for e in window)
    day = audit_service.list_entries(since="2026-10-03", limit=500)
    assert day == []
    print("Filter by time (date or timestamp)")

    _raises(ValueError, audit_service.list_entries, since="not a date")
    assert len(audit_service.list_entries(limit=0)) == 1
    assert len(audit_service.list_entries(limit=10**9)) <= 500
    print("A bad date is rejected; limit is clamped to 1..500")

    # ------------------------------------------------------------
    # RETENTION
    # ------------------------------------------------------------

    now = datetime(2027, 10, 2, 9, 30, tzinfo=timezone.utc)
    total = len(_rows(temp_db_path))
    purged = audit_service.purge_older_than(days=365, now=now)
    assert purged == total - 1
    left = _rows(temp_db_path)
    assert len(left) == 1 and left[0]["occurred_at"].startswith("2026-10-02T10")
    print(f"Retention purges entries older than a year ({purged}), keeps newer")

    assert audit_service.purge_older_than(days=365, now=now) == 0
    print("Purging again finds nothing")

    import shutil
    shutil.rmtree(temp_dir)

    print("\naudit_service smoke test passed.")
