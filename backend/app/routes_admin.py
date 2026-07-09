"""
routes_admin.py — Super-Admin only endpoints.

SECURITY MODEL:
  - /api/admin/login    — validates against env-stored credentials ONLY (no DB lookup)
  - /api/admin/*        — all other routes require a valid super_admin JWT
  - Rate limited to 10 req/min per IP (vs 60/min global)
  - All account creations are audited with createdBy field in MongoDB
"""

import logging
import secrets
import string
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth import (
    create_admin_token,
    hash_password,
    is_super_admin,
)
from app.cache import admin_rate_limiter
from app.config import settings
from app.db import get_db
from app.deps import require_super_admin
from app.schemas_auth import (
    AdminLoginRequest,
    AdminLoginResponse,
    CreateAccountRequest,
    CreateAccountResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client_ip(request: Request) -> str:
    """Extract real client IP from request, handling proxies."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    real_ip = request.headers.get("X-Real-IP")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"


def _check_admin_rate_limit(client_ip: str, endpoint: str) -> None:
    """Enforce strict admin rate limiting. Raises 429 if exceeded."""
    if not admin_rate_limiter.is_allowed(client_ip):
        logger.warning(
            f"Admin rate limit exceeded — IP: {client_ip} endpoint: {endpoint}"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait before trying again.",
            headers={"Retry-After": "60"},
        )


def _generate_passkey(length: int = 8) -> str:
    """Generate a unique workspace passkey for new companies."""
    alphabet = string.ascii_uppercase + string.digits
    alphabet = alphabet.replace("O", "").replace("I", "").replace("0", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _normalize_passkey(pk: str) -> str:
    return pk.replace("-", "").upper()


# ---------------------------------------------------------------------------
# POST /api/admin/login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(payload: AdminLoginRequest, request: Request):
    """
    Authenticate the super-admin using env-stored credentials.

    - Credentials are validated ONLY against ADMIN_EMAIL and ADMIN_PASSWORD_HASH in .env
    - No MongoDB lookup — prevents DB-based brute-force
    - Returns a short-lived JWT (1 hour) with role=super_admin
    - Rate limited: 10 req/min per IP
    """
    client_ip = _get_client_ip(request)
    _check_admin_rate_limit(client_ip, "/api/admin/login")

    # Validate against env credentials
    if not is_super_admin(payload.email, payload.password):
        # Log failed attempt without exposing which field was wrong
        logger.warning(
            f"Failed admin login attempt — IP: {client_ip} email: {payload.email[:3]}***"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
        )

    token = create_admin_token()
    logger.info(f"Super-admin logged in — IP: {client_ip}")

    return AdminLoginResponse(
        accessToken=token,
        role="super_admin",
        expiresInMinutes=settings.ADMIN_JWT_EXP_MINUTES,
    )


# ---------------------------------------------------------------------------
# POST /api/admin/create-account
# ---------------------------------------------------------------------------

@router.post("/create-account", response_model=CreateAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: CreateAccountRequest,
    request: Request,
    admin: dict = Depends(require_super_admin),
):
    """
    Create a new HR admin or employee account.

    - Requires a valid super_admin JWT (from /api/admin/login)
    - Password is hashed with bcrypt before storage
    - Rate limited: 10 req/min per IP
    - Full audit trail: createdBy field records the super-admin email
    - For hr_admin: creates a new company workspace (or joins existing via companyId)
    - For employee: requires a companyId or workspace passkey
    """
    client_ip = _get_client_ip(request)
    _check_admin_rate_limit(client_ip, "/api/admin/create-account")

    db = get_db()

    # email already normalized by field_validator in schema
    email = payload.email

    # Check for duplicate email
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{email}' already exists.",
        )

    company_id = payload.companyId
    company_name = "My Company"
    now = datetime.now(timezone.utc).isoformat()

    # ── HR Admin account ───────────────────────────────────────────────────
    if payload.role == "hr_admin":
        if payload.companyName and not company_id:
            # Create a brand-new company workspace
            company_name = payload.companyName.strip()
            company_id = str(uuid.uuid4())
            passkey = _generate_passkey()
            await db.companies.insert_one({
                "_id": company_id,
                "name": company_name,
                "passkey": passkey,
                "createdAt": now,
                "createdBy": settings.ADMIN_EMAIL,
                "settings": {},
            })
            logger.info(f"Created new company '{company_name}' with id {company_id}")

        elif company_id:
            # Join existing company
            company = await db.companies.find_one({"_id": company_id})
            if not company:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Company with id '{company_id}' not found.",
                )
            company_name = company.get("name", "My Company")
            # Backfill passkey if missing (data migration)
            if not company.get("passkey"):
                await db.companies.update_one(
                    {"_id": company_id},
                    {"$set": {"passkey": _generate_passkey()}},
                )

        else:
            # Auto-create a default company for this HR admin
            display_name = payload.fullName or email.split("@")[0]
            company_name = f"{display_name}'s Company"
            company_id = str(uuid.uuid4())
            passkey = _generate_passkey()
            await db.companies.insert_one({
                "_id": company_id,
                "name": company_name,
                "passkey": passkey,
                "createdAt": now,
                "createdBy": settings.ADMIN_EMAIL,
                "settings": {},
            })

    # ── Employee account ───────────────────────────────────────────────────
    elif payload.role == "employee":
        if payload.passkey:
            # Resolve via passkey
            normalised = _normalize_passkey(payload.passkey)
            company = await db.companies.find_one({"passkey": normalised})
            if not company:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Invalid workspace passkey. Please verify with your HR admin.",
                )
            company_id = str(company["_id"])
            company_name = company.get("name", "Your Company")

        elif company_id:
            company = await db.companies.find_one({"_id": company_id})
            if not company:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Company with id '{company_id}' not found.",
                )
            company_name = company.get("name", "Your Company")

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee accounts require a companyId or workspace passkey.",
            )

    # Hash password (bcrypt, cost factor 12 by default via gensalt())
    hashed_pwd = hash_password(payload.password)
    user_id = str(uuid.uuid4())

    user_doc = {
        "_id": user_id,
        "email": email,
        "passwordHash": hashed_pwd,
        "role": payload.role,
        "fullName": payload.fullName or "",
        "companyId": company_id,
        "createdAt": now,
        "createdBy": settings.ADMIN_EMAIL,   # audit trail
        "isActive": True,
        "lastLoginAt": None,
    }

    await db.users.insert_one(user_doc)

    logger.info(
        f"Account created — email: {email} role: {payload.role} "
        f"company: {company_name} by: {settings.ADMIN_EMAIL}"
    )

    return CreateAccountResponse(
        message="Account created successfully.",
        userId=user_id,
        email=email,
        role=payload.role,
        companyId=company_id,
        companyName=company_name,
        createdAt=now,
    )


# ---------------------------------------------------------------------------
# GET /api/admin/users
# ---------------------------------------------------------------------------

@router.get("/users")
async def list_users(
    request: Request,
    admin: dict = Depends(require_super_admin),
    page: int = 1,
    page_size: int = 20,
    role: str | None = None,
):
    """
    List all user accounts (paginated).

    - Requires super_admin JWT
    - Supports filtering by role: ?role=hr_admin or ?role=employee
    - Excludes passwordHash from response for security
    """
    client_ip = _get_client_ip(request)
    _check_admin_rate_limit(client_ip, "/api/admin/users")

    db = get_db()

    query: dict = {}
    if role and role in ("hr_admin", "employee"):
        query["role"] = role

    skip = (page - 1) * page_size
    cursor = (
        db.users.find(query, {"passwordHash": 0})
        .skip(skip)
        .limit(page_size)
        .sort("createdAt", -1)
    )
    users = await cursor.to_list(length=page_size)

    total = await db.users.count_documents(query)

    # Serialize fields
    serialized = []
    for u in users:
        serialized.append({
            "userId": str(u.get("_id", "")),
            "email": u.get("email", ""),
            "fullName": u.get("fullName", ""),
            "role": u.get("role", ""),
            "companyId": u.get("companyId", ""),
            "isActive": u.get("isActive", True),
            "createdAt": u.get("createdAt", ""),
            "createdBy": u.get("createdBy", ""),
            "lastLoginAt": u.get("lastLoginAt"),
        })

    return {
        "users": serialized,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": (total + page_size - 1) // page_size,
    }
