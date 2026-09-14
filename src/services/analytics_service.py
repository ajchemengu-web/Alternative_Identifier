import sqlite3
from datetime import datetime

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# docs/PRD.md §13 (Phase 3) names "full analytics (false-positive
# tracking, movement rates)" as a hard requirement, not a
# nice-to-have. This is built on real data, not invented metrics:
#
# - "False positive" needs a human decision — there's no ground
#   truth in the data to infer it from (a high recognition_score
#   doesn't mean the match was actually correct). So this adds a
#   real flagging mechanism: a Guard or Admin who discovers, after
#   the fact, that a VERIFIED access_logs entry matched the wrong
#   person marks it via flag_false_positive(). The rate below is
#   computed only over entries that could plausibly be flagged this
#   way (decision='VERIFIED', i.e. an auto-admitted match) — a
#   liveness failure or an admitted-guest re-entry was never a
#   "positive match" claim in the first place.
# - "Movement rates" is entrance/person_type traffic counts over
#   access_logs — the only real record of anyone moving through a
#   checkpoint that exists in this backend.


def flag_false_positive(access_log_id, reason, reviewed_by):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE access_logs
        SET
            false_positive = 1,
            false_positive_reason = ?,
            false_positive_reviewed_by = ?,
            false_positive_reviewed_at = ?
        WHERE id = ?
    """, (
        reason,
        reviewed_by,
        datetime.now().isoformat(),
        access_log_id
    ))

    connection.commit()

    updated = cursor.rowcount

    connection.close()

    return updated > 0


def _average(values):

    values = [value for value in values if value is not None]

    if not values:

        return None

    return sum(values) / len(values)


def get_summary(since=None):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    if since:

        cursor.execute("""
            SELECT
                person_type, entrance, decision,
                recognition_score, liveness_score, false_positive
            FROM access_logs
            WHERE timestamp >= ?
        """, (since.isoformat(),))

    else:

        cursor.execute("""
            SELECT
                person_type, entrance, decision,
                recognition_score, liveness_score, false_positive
            FROM access_logs
        """)

    rows = [dict(row) for row in cursor.fetchall()]

    connection.close()

    counts_by_decision = {}
    movement_by_entrance = {}
    movement_by_person_type = {}

    verified_count = 0
    false_positive_count = 0

    for row in rows:

        decision = row["decision"] or "UNKNOWN"
        counts_by_decision[decision] = counts_by_decision.get(decision, 0) + 1

        entrance = row["entrance"] or "UNKNOWN"
        movement_by_entrance[entrance] = movement_by_entrance.get(entrance, 0) + 1

        person_type = row["person_type"] or "UNKNOWN"
        movement_by_person_type[person_type] = (
            movement_by_person_type.get(person_type, 0) + 1
        )

        if decision == "VERIFIED":

            verified_count += 1

            if row["false_positive"]:

                false_positive_count += 1

    false_positive_rate = (
        false_positive_count / verified_count
        if verified_count > 0
        else None
    )

    return {

        "total_access_attempts": len(rows),

        "counts_by_decision": counts_by_decision,

        "movement_by_entrance": movement_by_entrance,

        "movement_by_person_type": movement_by_person_type,

        "verified_count": verified_count,

        "false_positive_count": false_positive_count,

        "false_positive_rate": false_positive_rate,

        "average_recognition_score": _average(
            [row["recognition_score"] for row in rows]
        ),

        "average_liveness_score": _average(
            [row["liveness_score"] for row in rows]
        )
    }
