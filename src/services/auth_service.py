import os
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import bcrypt
import jwt

from src.db import get_connection


# ============================================================
# WHAT THIS IS
# ============================================================
#
# Backend for the Enrollment Dashboard (docs/PRD.md §5): one place
# every role — Student, Lecturer, Guard, Staff, Admin (any tier) —
# gets provisioned, one place a login checks credentials and says
# which dashboard they land on, and (create_access_token /
# decode_access_token below) the request-level auth every other
# protected endpoint in src/api/main.py now depends on via
# src/api/deps.py — /recognize, /guard/*, /students, /guests,
# /access-logs, /enroll, /enroll/student-face were unauthenticated
# until this token layer existed.
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
# ACCESS TOKENS (request-level auth for every other endpoint)
# ============================================================

ACCESS_TOKEN_TTL = timedelta(hours=12)


@lru_cache(maxsize=1)
def _jwt_secret():

    secret = os.environ.get("JWT_SECRET")

    if not secret:

        print(
            "[auth_service] WARNING: JWT_SECRET is not set — using an "
            "insecure development-only default. Set JWT_SECRET (see "
            ".env.example) before deploying anywhere real."
        )

        secret = "dev-only-insecure-jwt-secret-change-me"

    return secret


def create_access_token(username, role, admin_tier):

    payload = {

        "sub": username,

        "role": role,

        "admin_tier": admin_tier,

        "exp": datetime.now(timezone.utc) + ACCESS_TOKEN_TTL
    }

    return jwt.encode(
        payload,
        _jwt_secret(),
        algorithm="HS256"
    )


def decode_access_token(token):

    try:

        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=["HS256"]
        )

    except jwt.PyJWTError:

        return None

    return {

        "username": payload.get("sub"),

        "role": payload.get("role"),

        "admin_tier": payload.get("admin_tier")
    }


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

def _validate_role_and_tier(role, admin_tier, location):

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

    if role == "GUARD":

        if not location:

            raise ValueError(
                "GUARD accounts require a location — which "
                "checkpoint they're posted at (docs/PRD.md §6.2)"
            )

    elif location is not None:

        raise ValueError(
            "location only applies to role=GUARD"
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
    temp_expires_at=None,
    location=None
):

    _validate_role_and_tier(role, admin_tier, location)

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
            temp_expires_at,
            location
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        username,
        hash_password(password),
        email,
        role,
        admin_tier,
        linked_person_id,
        temp_expires_at,
        location
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

        "location": location,

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
            location,
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

        "location": user["location"],

        "dashboard": resolve_dashboard(
            user["role"],
            user["admin_tier"]
        ),

        "access_token": create_access_token(
            user["username"],
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
