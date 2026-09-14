from fastapi import HTTPException

from src.services.auth_service import create_access_token
from src.api.deps import get_current_user, require_admin_tier, require_roles


def _expect_http_error(callable_, status_code):

    try:
        callable_()
        raise AssertionError(f"expected HTTPException {status_code}")
    except HTTPException as error:
        assert error.status_code == status_code, (
            f"expected {status_code}, got {error.status_code}"
        )


if __name__ == "__main__":

    print("Testing API auth dependencies...")

    guard_token = create_access_token("guard1", "GUARD", None)
    admin_token = create_access_token(
        "admin1", "ADMIN", "ORIGINAL"
    )
    temp_admin_token = create_access_token(
        "temp1", "ADMIN", "TEMPORARY"
    )

    # ------------------------------------------------------------
    # get_current_user
    # ------------------------------------------------------------

    _expect_http_error(
        lambda: get_current_user(authorization=None),
        401
    )
    print("Missing Authorization header -> 401. OK")

    _expect_http_error(
        lambda: get_current_user(authorization="NotBearer xyz"),
        401
    )
    print("Malformed Authorization header -> 401. OK")

    _expect_http_error(
        lambda: get_current_user(authorization="Bearer not-a-real-token"),
        401
    )
    print("Garbage token -> 401. OK")

    user = get_current_user(authorization=f"Bearer {guard_token}")
    assert user == {
        "username": "guard1",
        "role": "GUARD",
        "admin_tier": None
    }
    print("Valid guard token -> decoded correctly. OK")

    # ------------------------------------------------------------
    # require_roles
    # ------------------------------------------------------------

    admin_only = require_roles("ADMIN")

    _expect_http_error(
        lambda: admin_only(user=get_current_user(f"Bearer {guard_token}")),
        403
    )
    print("Guard token against require_roles('ADMIN') -> 403. OK")

    result = admin_only(user=get_current_user(f"Bearer {admin_token}"))
    assert result["username"] == "admin1"
    print("Admin token against require_roles('ADMIN') -> allowed. OK")

    guard_or_admin = require_roles("ADMIN", "GUARD")
    assert guard_or_admin(
        user=get_current_user(f"Bearer {guard_token}")
    )["username"] == "guard1"
    assert guard_or_admin(
        user=get_current_user(f"Bearer {admin_token}")
    )["username"] == "admin1"
    print("Multi-role require_roles('ADMIN', 'GUARD') -> allows both. OK")

    # ------------------------------------------------------------
    # require_admin_tier
    # ------------------------------------------------------------

    original_only = require_admin_tier("ORIGINAL")

    assert original_only(
        user=get_current_user(f"Bearer {admin_token}")
    )["admin_tier"] == "ORIGINAL"
    print("Original admin token against require_admin_tier('ORIGINAL') -> allowed. OK")

    _expect_http_error(
        lambda: original_only(
            user=get_current_user(f"Bearer {temp_admin_token}")
        ),
        403
    )
    print("Temporary admin token against require_admin_tier('ORIGINAL') -> 403. OK")

    _expect_http_error(
        lambda: original_only(user=get_current_user(f"Bearer {guard_token}")),
        403
    )
    print("Guard token against require_admin_tier('ORIGINAL') -> 403. OK")

    print("\napi deps smoke test passed.")
