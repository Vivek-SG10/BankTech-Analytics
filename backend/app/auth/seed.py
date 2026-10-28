"""
Development seed endpoint — creates demo accounts for all four roles.

ONLY available when ENVIRONMENT=development (never in production).
Call:  POST /api/v1/dev/seed

Demo accounts created
---------------------
admin@banktech.dev       / Demo1234! — admin
researcher@banktech.dev  / Demo1234! — researcher
manager@banktech.dev     / Demo1234! — manager
employee@banktech.dev    / Demo1234! — employee
customer@banktech.dev    / Demo1234! — customer

If an account already exists, it is left unchanged (idempotent).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.crud import create_user, get_user_by_email
from app.auth.schemas import UserOut
from app.auth.security import hash_password
from app.core.config import get_settings
from app.core.database import get_db

dev_router = APIRouter()

DEMO_PASSWORD = "Demo1234!"  # nosec — dev only, clearly labelled

DEMO_ACCOUNTS = [
    {"name": "Admin Demo",      "email": "admin@banktech.dev",      "role": "admin",      "department": "IT"},
    {"name": "Researcher Demo", "email": "researcher@banktech.dev",  "role": "researcher", "department": "Research"},
    {"name": "Manager Demo",    "email": "manager@banktech.dev",     "role": "manager",    "department": "Retail Banking"},
    {"name": "Employee Demo",   "email": "employee@banktech.dev",    "role": "employee",   "department": "Operations"},
    {"name": "Customer Demo",   "email": "customer@banktech.dev",    "role": "customer",   "department": None},
]


@dev_router.post(
    "/seed",
    response_model=list[UserOut],
    summary="[Dev only] Seed demo accounts for all roles",
    description=(
        "Creates one demo account per role using the password `Demo1234!`. "
        "**Only available in the `development` environment.** "
        "Existing accounts are skipped (idempotent)."
    ),
)
async def seed_demo_accounts(db: AsyncSession = Depends(get_db)) -> list[UserOut]:
    settings = get_settings()
    if settings.environment.lower() != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seed endpoint is only available in the development environment.",
        )

    created: list[UserOut] = []
    hashed_pw = hash_password(DEMO_PASSWORD)

    for acct in DEMO_ACCOUNTS:
        existing = await get_user_by_email(db, acct["email"])
        if existing is None:
            user = await create_user(
                db,
                name=acct["name"],
                email=acct["email"],
                hashed_password=hashed_pw,
                role=acct["role"],
                department=acct["department"],
            )
            created.append(UserOut.model_validate(user))

    return created
