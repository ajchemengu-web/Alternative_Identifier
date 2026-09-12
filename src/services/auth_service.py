import sqlite3
from datetime import datetime

import bcrypt

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# Backend for the Enrollment Dashboard (docs/PRD.md §5): one place
# every role — Student, Lecturer, Guard, Staff, Admin (any tier) —
# gets provisioned, and one place a login checks credentials and
# says which dashboard they land on.
#
# What this deliberately does NOT include yet: session tokens / JWTs
# / a real auth middleware protecting the other endpoints. Nothing
# else in this API is authenticated today (/recognize, /guard/*, the
# read endpoints are all open), so bolting a full session layer onto
# just this one feature would be inconsistent with where the rest of
# the prototype is. This gives the real credential check + password
# hashing + role/dashboard routing; wiring that into request-level
# auth is the natural next step once more of the API needs it.
#
# Also deliberately not included: actually emailing credentials.
# send_enrollment_email() below is a stub — it logs what would be
# sent instead of calling a real provider, the same way credential-
# dependent work (Supabase) was put on hold elsewhere. Wire it to a
# real provider once those credentials exist.


ROLES = {
    "STUDENT",
    "LECTURER",
    "GUARD",
    "STAFF",
    "ADMIN"
}

ADMIN_TIERS = {
    "ORIGINAL",
    "SECURITY",
    "TIMETABLING",
    "DEAN",
    "TEMPORARY"
}


# ============================================================
# PASSWORD HASHING
# ============================================================

def hash_password(password):

    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(password, password_hash):

    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8")
    )


# ============================================================
# ROLE / DASHBOARD ROUTING (docs/PRD.md §8, §9)
# ============================================================

def resolve_dashboard(role, admin_tier=None):

    if role == "STUDENT" or role == "LECTURER":

        return "smartattendance_app"

    if role == "GUARD":

        return "guard_dashboard"

    if role == "STAFF":

        # Staff are SmartAccess-only (docs/PRD.md §7.4) — there is
        # no portal for them beyond being enrolled for recognition.
        return "none"

    if role == "ADMIN":

        return {

            "ORIGINAL": "original_admin_dashboard",

            "SECURITY": "security_admin_dashboard",

            "TIMETABLING": "timetabling_admin_dashboard",

            "DEAN": "dean_admin_dashboard",

            "TEMPORARY": "enrollment_dashboard"

        }.get(admin_tier)

    return None


# ============================================================
# VALIDATION
# ============================================================

def _validate_role_and_tier(role, admin_tier):

    if role not in ROLES:

        raise ValueError(
            f"Unknown role: {role}"
        )

    if role == "ADMIN":

        if admin_tier not in ADMIN_TIERS:

            raise ValueError(
                f"Unknown admin_tier: {admin_tier}"
            )

    elif admin_tier is not None:

        raise ValueError(
            "admin_tier only applies to role=ADMIN"
        )


# ============================================================
# CREATE USER (ENROLLMENT)
# ============================================================

def create_user(
    username,
    password,
    email,
    role,
    admin_tier=None,
    linked_person_id=None,
    temp_expires_at=None
):

    _validate_role_and_tier(role, admin_tier)

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO users (
            username,
            password_hash,
            email,
            role,
            admin_tier,
            linked_person_id,
            temp_expires_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        username,
        hash_password(password),
        email,
        role,
        admin_tier,
        linked_person_id,
        temp_expires_at
    ))

    connection.commit()

    connection.close()

    send_enrollment_email(
        username=username,
        email=email,
        password=password,
        role=role,
        admin_tier=admin_tier
    )

    return {

        "username": username,

        "email": email,

        "role": role,

        "admin_tier": admin_tier,

        "dashboard": resolve_dashboard(role, admin_tier)
    }


# ============================================================
# AUTHENTICATE (LOGIN)
# ============================================================

def authenticate(username, password):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            username,
            password_hash,
            email,
            role,
            admin_tier,
            temp_expires_at,
            is_active
        FROM users
        WHERE username = ?
    """, (
        username,
    ))

    user = cursor.fetchone()

    if user is None:

        connection.close()

        return None

    if not user["is_active"]:

        connection.close()

        return None

    if user["temp_expires_at"]:

        expires_at = datetime.fromisoformat(
            user["temp_expires_at"]
        )

        if datetime.now() >= expires_at:

            # A temporary admin whose task window has passed loses
            # access on their next login attempt, not just at the
            # moment an admin explicitly deactivates them.
            cursor.execute("""
                UPDATE users
                SET is_active = 0
                WHERE id = ?
            """, (
                user["id"],
            ))

            connection.commit()
            connection.close()

            return None

    connection.close()

    if not verify_password(password, user["password_hash"]):

        return None

    return {

        "username": user["username"],

        "email": user["email"],

        "role": user["role"],

        "admin_tier": user["admin_tier"],

        "dashboard": resolve_dashboard(
            user["role"],
            user["admin_tier"]
        )
    }


# ============================================================
# MARK A TEMPORARY ADMIN'S TASK COMPLETE (docs/PRD.md §8)
# ============================================================

def mark_temporary_admin_task_complete(username):

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT admin_tier
        FROM users
        WHERE username = ?
    """, (
        username,
    ))

    user = cursor.fetchone()

    if user is None:

        connection.close()

        return {
            "success": False,
            "message": "User not found"
        }

    if user["admin_tier"] != "TEMPORARY":

        connection.close()

        return {
            "success": False,
            "message": "User is not a temporary admin"
        }

    cursor.execute("""
        UPDATE users
        SET is_active = 0
        WHERE username = ?
    """, (
        username,
    ))

    connection.commit()

    connection.close()

    return {
        "success": True,
        "username": username,
        "message": "Temporary admin credentials deactivated"
    }


# ============================================================
# ENROLLMENT EMAIL (STUB — see note at top of file)
# ============================================================

def send_enrollment_email(username, email, password, role, admin_tier):

    print(
        "[ENROLLMENT EMAIL — STUB, NOT SENT] "
        f"To: {email} | "
        f"Role: {role}"
        f"{f' ({admin_tier})' if admin_tier else ''} | "
        f"Username: {username} | "
        "TODO: wire to a real email provider once credentials exist"
    )
