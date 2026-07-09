"""
routes_auth.py — Authentication: signup, login, logout, workspace passkey lookup
"""

import secrets
import string
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.db import get_db
from app.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.deps import require_role
from app.schemas_auth import (
    LoginRequest,
    LoginResponse,
    SignupResponse,
    SignupRequest,
    WorkspaceInfoResponse,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_passkey(length: int = 8) -> str:
    """Generate a short, memorable workspace passkey (uppercase alphanumeric)."""
    alphabet = string.ascii_uppercase + string.digits
    # Remove ambiguous chars: O, 0, I, 1
    alphabet = alphabet.replace("O", "").replace("I", "").replace("0", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _format_passkey(raw: str) -> str:
    """Format passkey as XXXX-XXXX for readability."""
    raw = raw.upper()
    if len(raw) == 8:
        return f"{raw[:4]}-{raw[4:]}"
    return raw


def _normalize_passkey(pk: str) -> str:
    """Strip dashes, uppercase — canonical form for DB storage and lookup."""
    return pk.replace("-", "").upper()


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------

@router.post("/signup", response_model=SignupResponse)
async def signup(payload: SignupRequest):
    db = get_db()

    # Normalise email
    email = payload.email.strip().lower()

    # Check existing user
    existing_user = await db.users.find_one({"email": email})

    company_id = payload.companyId
    company_name = "My Company"

    # ── Employee ──────────────────────────────────────────────────────────────
    if payload.role == "employee":
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee email not found in database. Please ask your HR admin to add you.",
            )
        if existing_user.get("role") != "employee":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered with a different role.",
            )

        # Support passkey-based lookup (preferred) OR direct companyId
        if payload.passkey:
            normalised = _normalize_passkey(payload.passkey)
            company = await db.companies.find_one({"passkey": normalised})
            if not company:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Invalid workspace passkey. Please check with your HR admin.",
                )
            if existing_user.get("companyId") != str(company["_id"]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Workspace passkey does not match the company you are registered with.",
                )
            company_id = str(company["_id"])
            company_name = company.get("name", "Your Company")

        elif company_id:
            if existing_user.get("companyId") != company_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Company ID does not match the company you are registered with.",
                )
            company = await db.companies.find_one({"_id": company_id})
            if not company:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Company not found",
                )
            company_name = company.get("name", "Your Company")

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employees must provide a workspace passkey or company ID to join.",
            )

        hashed_pwd = hash_password(payload.password)
        now = datetime.now(timezone.utc).isoformat()
        await db.users.update_one(
            {"_id": existing_user["_id"]},
            {
                "$set": {
                    "passwordHash": hashed_pwd,
                    "updatedAt": now,
                },
                "$unset": {"tempPassword": ""},
            }
        )
        return SignupResponse(
            message="User created successfully",
            companyId=company_id,
            companyName=company_name,
        )

    # ── HR Admin ──────────────────────────────────────────────────────────────
    elif payload.role == "hr_admin":
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        if payload.companyName and not company_id:
            company_name = payload.companyName.strip()
            company_id = str(uuid.uuid4())
            passkey = _generate_passkey()
            await db.companies.insert_one({
                "_id": company_id,
                "name": company_name,
                "passkey": passkey,          # raw 8-char, stored normalised
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "settings": {},
            })
        elif company_id:
            # Existing company
            company = await db.companies.find_one({"_id": company_id})
            if company:
                company_name = company.get("name", "My Company")
                # Backfill passkey if missing
                if not company.get("passkey"):
                    await db.companies.update_one(
                        {"_id": company_id},
                        {"$set": {"passkey": _generate_passkey()}},
                    )
        else:
            # No name, no ID — create default company
            company_id = str(uuid.uuid4())
            passkey = _generate_passkey()
            await db.companies.insert_one({
                "_id": company_id,
                "name": "My Company",
                "passkey": passkey,
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "settings": {},
            })

        user_id = str(uuid.uuid4())
        hashed_pwd = hash_password(payload.password)
        now = datetime.now(timezone.utc).isoformat()
        await db.users.insert_one({
            "_id": user_id,
            "email": email,
            "passwordHash": hashed_pwd,
            "role": payload.role,
            "companyId": company_id,
            "createdAt": now,
        })

        return SignupResponse(
            message="User created successfully",
            companyId=company_id,
            companyName=company_name,
        )


# ---------------------------------------------------------------------------
# Workspace passkey lookup (for employee registration preview)
# ---------------------------------------------------------------------------

@router.get("/workspace/{passkey}", response_model=WorkspaceInfoResponse)
async def get_workspace_by_passkey(passkey: str):
    """Resolve a passkey to company info — used on the signup form for confirmation."""
    normalised = _normalize_passkey(passkey)
    db = get_db()
    company = await db.companies.find_one({"passkey": normalised})
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No workspace found with this passkey.",
        )
    return WorkspaceInfoResponse(
        companyId=str(company["_id"]),
        companyName=company.get("name", "Unknown Company"),
        passkey=_format_passkey(normalised),
    )


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest):
    db = get_db()
    email = payload.email.strip().lower()

    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not verify_password(payload.password, user.get("passwordHash") or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    role = user.get("role")
    company_id = user.get("companyId")
    if role not in ("hr_admin", "employee") or not company_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user record",
        )

    token = create_access_token(user_id=str(user.get("_id")), role=role, company_id=company_id)
    return LoginResponse(accessToken=token, role=role, companyId=company_id)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout():
    # Client-side logout (drop token). Refresh token blacklisting can be added later.
    return {"message": "logged out"}
