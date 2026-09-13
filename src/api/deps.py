from fastapi import Depends, Header, HTTPException

from src.services.auth_service import decode_access_token


# ============================================================
# WHAT THIS IS
# ============================================================
#
# FastAPI dependencies gating every endpoint that isn't meant to be
# public. Every protected route in src/api/main.py takes one of
# these via `Depends(...)`. A request needs an
# `Authorization: Bearer <token>` header carrying the access_token
# POST /login returned; the Smart Gen web platform (Smart-gen.com)
# stores that token server-side in its own session cookie and
# forwards it on every proxied call — the browser itself never sees
# the backend's JWT directly.


def get_current_user(authorization: str = Header(default=None)):

    if not authorization or not authorization.startswith("Bearer "):

        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header"
        )

    token = authorization[len("Bearer "):]

    user = decode_access_token(token)

    if user is None:

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token"
        )

    return user


def require_roles(*roles):

    def checker(user: dict = Depends(get_current_user)):

        if user["role"] not in roles:

            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions for this role"
            )

        return user

    return checker


def require_admin_tier(*tiers):

    def checker(user: dict = Depends(get_current_user)):

        if user["role"] != "ADMIN" or user.get("admin_tier") not in tiers:

            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions for this admin tier"
            )

        return user

    return checker
