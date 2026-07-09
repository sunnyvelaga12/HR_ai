import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

def _jwt_secret() -> str:
    secret = settings.JWT_SECRET
    if not secret:
        raise RuntimeError("JWT_SECRET is not set in .env")
    return secret


def _jwt_exp_minutes() -> int:
    return settings.JWT_EXP_MINUTES


def hash_password(password: str) -> str:
    try:
        import bcrypt
    except ImportError as exc:
        raise RuntimeError("bcrypt is not installed") from exc

    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        import bcrypt
    except ImportError as exc:
        raise RuntimeError("bcrypt is not installed") from exc

    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(*, user_id: str, role: str, company_id: str) -> str:
    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError("pyjwt is not installed") from exc

    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=_jwt_exp_minutes())

    payload = {
        "sub": user_id,
        "role": role,
        "companyId": company_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    token = jwt.encode(payload, _jwt_secret(), algorithm="HS256")
    return token


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError("pyjwt is not installed") from exc

    try:
        return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ---------------------------------------------------------------------------
# Super-Admin Auth (env-credential based — never touches the DB)
# ---------------------------------------------------------------------------

def is_super_admin(email: str, password: str) -> bool:
    """Validate super-admin credentials against env-stored values.

    The super-admin account is NOT stored in MongoDB — it lives entirely
    in environment variables so it cannot be brute-forced via the DB.
    """
    admin_email = settings.ADMIN_EMAIL.strip().lower()
    admin_hash = settings.ADMIN_PASSWORD_HASH.strip()

    if not admin_email or not admin_hash:
        logger.error("ADMIN_EMAIL or ADMIN_PASSWORD_HASH not configured in .env")
        return False

    if email.strip().lower() != admin_email:
        return False

    return verify_password(password, admin_hash)


def create_admin_token() -> str:
    """Create a short-lived JWT for the super-admin session."""
    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError("pyjwt is not installed") from exc

    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.ADMIN_JWT_EXP_MINUTES)

    payload = {
        "sub": "super_admin",
        "role": "super_admin",
        "companyId": "__system__",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")
