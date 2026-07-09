from typing import Any
import os

from fastapi import Depends, Header, HTTPException, status

from app.auth import decode_access_token


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header")
    return parts[1]


def get_current_user(token: str = Depends(get_bearer_token)) -> dict[str, Any]:
    return decode_access_token(token)


def require_role(*, role: str):
    def _dep(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if user.get("role") != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return _dep


def require_super_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Dependency that ensures the caller is authenticated as super_admin.

    Only the system owner (credentials stored in .env) can pass this check.
    Any other role — including hr_admin — will be rejected with 403 Forbidden.
    """
    if user.get("role") != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Super admin credentials required.",
        )
    return user
