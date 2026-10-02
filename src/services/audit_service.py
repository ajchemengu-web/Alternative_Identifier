import json
import sqlite3
from datetime import datetime, timedelta, timezone

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# The read audit log: a record of who looked at personal data, and
# when (docs/DPIA.md R3). Role and tier checks stop the wrong people
# reading things; this answers the other question — of the people who
# are allowed, who actually did, so misuse by someone with legitimate
# access can be noticed and investigated.
#
# What is recorded per read: the account (username, role, tier, and a
# Dean's department), what kind of read (`action`, e.g.
# "students.list"), which record when it was about one (`subject_id`,
# e.g. a watchlist target or a student), and the filters the caller
# supplied. Never the data that was returned.
#
# Repeated identical reads are coalesced into one row (`times`,
# `last_seen_at`) within COALESCE_SECONDS, otherwise a guard's
# dashboard polling the access log every few seconds would write
# thousands of rows an hour and bury everything else.
#
# Failing closed: if a read cannot be recorded the read is refused
# (AuditUnavailableError -> HTTP 503 in src/api/deps.py). An audit log
# that silently has gaps is worse than none.
#
# What this does NOT give you, so nobody assumes more:
#   - It is not tamper-evident. Someone with direct write access to the
#     database can edit or delete rows; the application itself offers
#     no way to (only the age-based purge below). Protect it at the
#     database level — a role that can only INSERT, or copying it to
#     storage the operators don't control.
#   - It covers reads through this API. It does not see anyone reading
#     the database, the data folder, backups or the server directly.
#   - Not every read is logged: aggregates (analytics, department
#     summaries), camera/unit/timetable lists and a person's own data
#     are left out, as they aren't a view into other people's records.
#   - Entries are themselves personal data about staff; they are purged
#     after AUDIT_RETENTION_DAYS (default one year).


COALESCE_SECONDS = 300
AUDIT_RETENTION_DAYS = 365

_MAX_PARAMS = 10
_MAX_VALUE_LENGTH = 120
_SECRET_WORDS = ("token", "password", "secret", "authorization")


class AuditUnavailableError(Exception):

    pass


def _now():

    return datetime.now(timezone.utc)


def _stamp(moment):

    return moment.isoformat(timespec="seconds")


def _clean_params(params):

    cleaned = {}

    for key in sorted((params or {}).keys()):

        if len(cleaned) >= _MAX_PARAMS:

            break

        if any(word in key.lower() for word in _SECRET_WORDS):

            continue

        value = params[key]

        if value is None or value == "":

            continue

        cleaned[str(key)[:60]] = str(value)[:_MAX_VALUE_LENGTH]

    return json.dumps(cleaned, sort_keys=True)


# ============================================================
# READINESS (checked once at server startup)
# ============================================================

def require_ready():

    try:

        connection = get_connection()

        cursor = connection.cursor()

        cursor.execute("SELECT 1 FROM audit_log WHERE 1 = 0")

        connection.close()

    except Exception as error:

        raise RuntimeError(
            "The read audit log table is missing, so the server will "
            "not start: reads of personal data cannot be recorded. Run "
            "`python -m src.upgrade_audit_log_table` (SQLite) or apply "
            f"supabase/schema.sql (Postgres). ({error})"
        )


# ============================================================
# RECORD A READ
# ============================================================

def record_read(user, action, subject=None, params=None, now=None):

    now = now or _now()

    subject = "" if subject is None else str(subject)[:_MAX_VALUE_LENGTH]

    params_json = _clean_params(params)

    window_start = _stamp(now - timedelta(seconds=COALESCE_SECONDS))

    try:

        connection = get_connection()

        connection.row_factory = sqlite3.Row

        cursor = connection.cursor()

        cursor.execute(
            "SELECT id FROM audit_log "
            "WHERE username = ? AND action = ? AND subject_id = ? "
            "AND params = ? AND occurred_at >= ? "
            "ORDER BY id DESC LIMIT 1",
            (user["username"], action, subject, params_json, window_start)
        )

        existing = cursor.fetchone()

        if existing is not None:

            cursor.execute(
                "UPDATE audit_log SET times = times + 1, last_seen_at = ? "
                "WHERE id = ?",
                (_stamp(now), existing["id"])
            )

        else:

            cursor.execute(
                "INSERT INTO audit_log "
                "(occurred_at, last_seen_at, times, username, role, "
                "admin_tier, department, action, subject_id, params) "
                "VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _stamp(now),
                    _stamp(now),
                    user["username"],
                    user.get("role"),
                    user.get("admin_tier"),
                    user.get("department"),
                    action,
                    subject,
                    params_json,
                )
            )

        connection.commit()

        connection.close()

    except Exception as error:

        raise AuditUnavailableError(str(error))


# ============================================================
# READ THE LOG (Original Admin only — enforced at the route)
# ============================================================

def list_entries(
    username=None,
    action=None,
    subject=None,
    since=None,
    until=None,
    limit=100
):

    limit = max(1, min(int(limit), 500))

    query = (
        "SELECT id, occurred_at, last_seen_at, times, username, role, "
        "admin_tier, department, action, subject_id, params "
        "FROM audit_log WHERE 1=1"
    )

    values = []

    if username:

        query += " AND username = ?"

        values.append(username)

    if action:

        query += " AND action = ?"

        values.append(action)

    if subject:

        query += " AND subject_id = ?"

        values.append(subject)

    if since:

        query += " AND occurred_at >= ?"

        values.append(_normalise_bound(since))

    if until:

        query += " AND occurred_at <= ?"

        values.append(_normalise_bound(until))

    query += " ORDER BY id DESC LIMIT ?"

    values.append(limit)

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute(query, values)

    rows = cursor.fetchall()

    connection.close()

    entries = []

    for row in rows:

        entry = {key: row[key] for key in row.keys()}

        entry["params"] = json.loads(entry["params"] or "{}")

        entries.append(entry)

    return entries


def _normalise_bound(text):

    # Accept "2026-10-01" or a full timestamp; the stored values are
    # UTC ISO strings, which compare correctly as text.
    try:

        parsed = datetime.fromisoformat(text)

    except ValueError:

        raise ValueError(
            f"'{text}' is not a date or ISO timestamp (e.g. 2026-10-01)."
        )

    if parsed.tzinfo is None:

        parsed = parsed.replace(tzinfo=timezone.utc)

    return _stamp(parsed.astimezone(timezone.utc))


# ============================================================
# RETENTION
# ============================================================

def purge_older_than(days=None, now=None):

    days = AUDIT_RETENTION_DAYS if days is None else days

    cutoff = _stamp((now or _now()) - timedelta(days=days))

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM audit_log WHERE last_seen_at < ?",
        (cutoff,)
    )

    count = cursor.fetchone()[0]

    cursor.execute(
        "DELETE FROM audit_log WHERE last_seen_at < ?",
        (cutoff,)
    )

    connection.commit()

    connection.close()

    return count
