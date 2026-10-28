"""
Database CRUD operations for users.

All functions accept an AsyncSession and return ORM objects or None.
Business logic (password hashing, token creation) lives in the router/security layer.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import UserOrm


async def get_user_by_email(db: AsyncSession, email: str) -> UserOrm | None:
    """Return the user with *email*, or None if not found."""
    result = await db.execute(select(UserOrm).where(UserOrm.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> UserOrm | None:
    """Return the user with *user_id*, or None if not found."""
    result = await db.execute(select(UserOrm).where(UserOrm.id == user_id))
    return result.scalar_one_or_none()


async def list_users(db: AsyncSession) -> list[UserOrm]:
    """Return all users ordered by creation time. Admin-only operation."""
    result = await db.execute(select(UserOrm).order_by(UserOrm.created_at))
    return list(result.scalars().all())


async def create_user(
    db: AsyncSession,
    *,
    name: str,
    email: str,
    hashed_password: str,
    role: str = "customer",
    department: str | None = None,
) -> UserOrm:
    """Insert a new user row and return it."""
    user = UserOrm(
        name=name,
        email=email,
        hashed_password=hashed_password,
        role=role,
        department=department,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def set_user_role(db: AsyncSession, user: UserOrm, new_role: str) -> UserOrm:
    """
    Change *user*'s role to *new_role*.
    Caller is responsible for verifying the actor has admin privileges.
    """
    user.role = new_role
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def set_user_active(db: AsyncSession, user: UserOrm, *, active: bool) -> UserOrm:
    """Activate or deactivate a user account."""
    user.is_active = active
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
