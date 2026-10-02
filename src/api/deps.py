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


def require_access(roles=(), admin_tiers=()):

    # For endpoints that serve some non-admin roles AND specific admin
    # tiers (e.g. a guard or the Original/Security admin). An ADMIN is
    # let in only if their tier is listed — "any admin" is not enough.
    def checker(user: dict = Depends(get_current_user)):

        if user["role"] in roles:

            return user

        if user["role"] == "ADMIN" and user.get("admin_tier") in admin_tiers:

            return user

        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions for this role or admin tier"
        )

    return checker


def scope_department(user, requested=None):

    """The department a request is allowed to look at.

    A Dean sees their own school only. What they ask for is checked
    against the department signed into their token, never trusted:
    omitting it gives their school, naming another one is refused. Any
    other caller is returned `requested` unchanged (None = everything).
    A Dean token with no department fails closed rather than falling
    back to a system-wide view.
    """

    if user.get("role") != "ADMIN" or user.get("admin_tier") != "DEAN":

        return requested

    own = (user.get("department") or "").strip()

    if not own:

        raise HTTPException(
            status_code=403,
            detail=(
                "This Dean account has no department assigned. Ask the "
                "Original Admin to set one, then sign in again."
            )
        )

    if requested and requested.strip().casefold() != own.casefold():

        raise HTTPException(
            status_code=403,
            detail="A Dean can only view their own department."
        )

    return own
