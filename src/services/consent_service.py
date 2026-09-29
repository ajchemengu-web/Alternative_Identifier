import os
import sqlite3

from src.db import get_connection as _get_raw_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# Records, per student, that they agreed to their face being turned
# into a facial template and matched at campus checkpoints and in
# classrooms. A facial template is sensitive personal data under
# Kenya's Data Protection Act, and the regulator's biometric guidance
# and the 2025 KBC High Court ruling both put the burden on the
# deploying organisation to show a lawful basis, a completed impact
# assessment, and that the person can actually say no and take it
# back. This is the "record what was agreed, when, and let them undo
# it" part of that; it is not legal advice, and the notice text below
# is a starting draft for the institution's own counsel to review.
#
# Design rules enforced here and in enrollment_service.py:
#   - No facial template is created without a consent record — the
#     student's own (channel SELF), or, for admin-run enrollment, an
#     admin's explicit confirmation that the student consented
#     (channel ADMIN_ASSISTED, with who confirmed it).
#   - Consent is tied to a notice version. If the notice text changes
#     materially, bump NOTICE_VERSION and existing consents stop
#     counting as active (needs_reconsent) — people are asked again
#     rather than silently held to text they never saw.
#   - Withdrawal is real: it marks the consent withdrawn AND the
#     enrollment_service deletes the stored template. Consent rows
#     themselves are kept as an audit trail.

NOTICE_VERSION = "2026-09-v1"

CHANNEL_SELF = "SELF"
CHANNEL_ADMIN_ASSISTED = "ADMIN_ASSISTED"


class ConsentRequiredError(Exception):

    pass


def get_connection():

    connection = _get_raw_connection()

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# THE NOTICE (what the person is shown before agreeing)
# ============================================================
#
# Served by the API rather than hardcoded in each client, so the web
# dashboards and the SmartAttendance app can never drift out of sync
# with what was actually recorded against NOTICE_VERSION.

def get_notice():

    controller = os.environ.get(
        "CONSENT_CONTROLLER_NAME",
        "Your institution (the data controller)"
    )

    contact = os.environ.get(
        "CONSENT_CONTACT",
        "your institution's data protection officer"
    )

    return {

        "version": NOTICE_VERSION,

        "title": "Facial recognition consent",

        "controller": controller,

        "contact": contact,

        "sections": [

            {
                "heading": "What we collect",
                "body": (
                    "A numerical template of your face, made from the "
                    "photos you take now. The photos themselves are "
                    "processed to make the template and are not kept. "
                    "Each time the template is matched we also record "
                    "when, where, and how confident the match was."
                )
            },

            {
                "heading": "Why we collect it",
                "body": (
                    "Only for two things: recognising you at campus "
                    "and hostel checkpoints, and recording your "
                    "attendance in classes you are enrolled in. It is "
                    "not used for any other purpose."
                )
            },

            {
                "heading": "Who can see it",
                "body": (
                    "The template is used automatically by the "
                    "recognition system and is not shown to people. "
                    "Access and attendance records can be seen by "
                    "authorised staff and, for classes you attend, by "
                    "your lecturer."
                )
            },

            {
                "heading": "How long we keep it",
                "body": (
                    "Until you withdraw your consent, or you leave the "
                    "institution and an administrator deletes your "
                    "data."
                )
            },

            {
                "heading": "Your choice and your rights",
                "body": (
                    "You do not have to agree. If you decline, contact "
                    "your institution about an alternative way to "
                    "record attendance and gain access. If you agree, "
                    "you can withdraw at any time from your Profile; "
                    "your face template is then deleted. You may also "
                    "ask to see, correct, or erase your data by "
                    "contacting the data controller."
                )
            },
        ],
    }


# ============================================================
# RECORDING / CHECKING CONSENT
# ============================================================

def _active_row(cursor, student_id):

    cursor.execute(
        "SELECT * FROM biometric_consents "
        "WHERE student_id = ? AND withdrawn_at IS NULL "
        "AND notice_version = ? "
        "ORDER BY id DESC",
        (student_id, NOTICE_VERSION)
    )

    return cursor.fetchone()


def has_active_consent(student_id):

    connection = get_connection()

    row = _active_row(connection.cursor(), student_id)

    connection.close()

    return row is not None


def record_consent(student_id, channel, recorded_by=None):

    connection = get_connection()

    cursor = connection.cursor()

    existing = _active_row(cursor, student_id)

    if existing is None:

        cursor.execute(
            "INSERT INTO biometric_consents "
            "(student_id, notice_version, channel, recorded_by) "
            "VALUES (?, ?, ?, ?)",
            (student_id, NOTICE_VERSION, channel, recorded_by)
        )

        connection.commit()

    connection.close()

    return get_status(student_id)


def withdraw_consent(student_id):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        "UPDATE biometric_consents SET withdrawn_at = CURRENT_TIMESTAMP "
        "WHERE student_id = ? AND withdrawn_at IS NULL",
        (student_id,)
    )

    withdrawn = cursor.rowcount

    connection.commit()

    connection.close()

    return withdrawn > 0


def get_status(student_id):

    connection = get_connection()

    cursor = connection.cursor()

    active = _active_row(cursor, student_id)

    # A consent that's still un-withdrawn but was given against an
    # older notice version: not active, but the person should be
    # asked again rather than treated as never having engaged.
    cursor.execute(
        "SELECT COUNT(*) AS n FROM biometric_consents "
        "WHERE student_id = ? AND withdrawn_at IS NULL "
        "AND notice_version != ?",
        (student_id, NOTICE_VERSION)
    )

    stale = cursor.fetchone()["n"] > 0

    connection.close()

    return {

        "consent_active": active is not None,

        "notice_version": active["notice_version"] if active else None,

        "granted_at": active["granted_at"] if active else None,

        "channel": active["channel"] if active else None,

        "needs_reconsent": active is None and stale,

        "current_notice_version": NOTICE_VERSION,
    }


def students_with_active_consent():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        "SELECT DISTINCT student_id FROM biometric_consents "
        "WHERE withdrawn_at IS NULL AND notice_version = ?",
        (NOTICE_VERSION,)
    )

    ids = {row["student_id"] for row in cursor.fetchall()}

    connection.close()

    return ids
