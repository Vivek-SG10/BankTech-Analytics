"""
Pydantic schemas for the auth endpoints.

Separate from ORM models — keeps the HTTP contract explicit and
prevents accidental exposure of internal fields (e.g. hashed_password).
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

VALID_ROLES = ("admin", "researcher", "manager", "employee", "customer")
SELF_REGISTER_ROLES = ("manager", "employee", "customer")   # admin/researcher assigned by admin

# ── Request bodies ────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    # Public registration restricted to non-privileged roles
    role: str = Field(
        default="customer",
        pattern=f"^({'|'.join(SELF_REGISTER_ROLES)})$",
        description="Allowed values for self-registration: manager, employee, customer. "
                    "Admin / researcher roles are assigned by an administrator.",
    )
    department: str | None = Field(default=None, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SetRoleRequest(BaseModel):
    """Body for PATCH /auth/users/{id}/role — admin only."""
    role: str = Field(
        ...,
        pattern=f"^({'|'.join(VALID_ROLES)})$",
        description=f"One of: {', '.join(VALID_ROLES)}",
    )


class SetActiveRequest(BaseModel):
    """Body for PATCH /auth/users/{id}/active — admin only."""
    is_active: bool


# ── Response bodies ───────────────────────────────────────────────────────────

class UserOut(BaseModel):
    """Safe user representation — never includes hashed_password."""
    id: str
    name: str
    email: str
    role: str
    department: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
