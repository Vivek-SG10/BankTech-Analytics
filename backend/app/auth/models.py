"""
SQLAlchemy ORM model for the users table.

This replaces the Phase-0 Pydantic-only stub in app/models/user.py.
The ORM model is imported by Alembic's env.py via app.db.base so that
`alembic revision --autogenerate` can detect it.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Single declarative base — import this everywhere, not individual classes."""


class UserOrm(Base):
    """
    Persistent user record.

    Roles: admin | researcher | manager | employee | customer
    Passwords are stored as bcrypt hashes — never plaintext.
    """

    __tablename__ = "users"

    id: str = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: str = Column(String(120), nullable=False)
    email: str = Column(String(254), unique=True, index=True, nullable=False)
    hashed_password: str = Column(String(72), nullable=False)  # bcrypt is at most 72 chars
    role: str = Column(String(20), nullable=False, default="customer")
    department: str | None = Column(String(100), nullable=True)
    is_active: bool = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
