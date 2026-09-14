import sqlite3

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# SmartAccess "live" target alerting (docs/PRD.md §8, Security Admin
# dashboard): a queue of unacknowledged TARGET_ALERT access_logs rows
# (access_service.py's TARGET_MATCH branch, watchlist_service.py) —
# every live target sighting until a Security/Original Admin
# acknowledges it. There's no push/email/SMS infrastructure or
# credentials available to this codebase yet (consistent with
# camera_service.py holding anything credential-related until real
# infrastructure exists), so "live" means a dashboard poll against
# this queue rather than an outbound notification — the acknowledged
# state itself is what makes that poll worth doing.


def _row_to_dict(row):

    return dict(row) if row is not None else None


def list_pending_alerts():

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT * FROM access_logs
        WHERE decision = 'TARGET_ALERT' AND alert_acknowledged = 0
        ORDER BY timestamp DESC, id DESC
    """)

    rows = [_row_to_dict(row) for row in cursor.fetchall()]

    for row in rows:

        cursor.execute(
            "SELECT full_name, reason FROM watchlist_targets "
            "WHERE target_id = ?",
            (row["person_identifier"],)
        )

        target = cursor.fetchone()

        row["full_name"] = target["full_name"] if target else None
        row["reason"] = target["reason"] if target else None

    connection.close()

    return rows


def acknowledge_alert(access_log_id, acknowledged_by):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE access_logs
        SET alert_acknowledged = 1,
            alert_acknowledged_by = ?,
            alert_acknowledged_at = CURRENT_TIMESTAMP
        WHERE id = ? AND decision = 'TARGET_ALERT' AND alert_acknowledged = 0
    """, (
        acknowledged_by,
        access_log_id
    ))

    connection.commit()

    updated = cursor.rowcount

    connection.close()

    return updated > 0
