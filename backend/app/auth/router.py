"""
Auth + user-management endpoints:

  POST   /api/v1/auth/register          — public: create account, return JWT
  POST   /api/v1/auth/login             — public: authenticate, return JWT
  GET    /api/v1/auth/me                — authenticated: return own profile
  POST   /api/v1/auth/logout            — authenticated: stateless JWT logout
  GET    /api/v1/auth/users             — admin only: list all users
  PATCH  /api/v1/auth/users/{id}/role   — admin only: change a user's role
  PATCH  /api/v1/auth/users/{id}/active — admin only: activate/deactivate account

Role assignment policy
----------------------
- Public registration accepts: manager, employee, customer.
- admin and researcher roles can ONLY be assigned by an existing admin via PATCH.
- Admins cannot demote themselves (prevents accidental lockout).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.crud import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    list_users,
    set_user_active,
    set_user_role,
)
from app.auth.deps import get_current_user, require_roles
from app.auth.models import UserOrm
from app.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    SetActiveRequest,
    SetRoleRequest,
    TokenResponse,
    UserOut,
)
from app.auth.security import create_access_token, hash_password, verify_password
from app.core.database import get_db

auth_router = APIRouter()


# ── Register ──────────────────────────────────────────────────────────────────

@auth_router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new participant account",
    description=(
        "Creates a new user account and immediately returns a JWT. "
        "Role is restricted to `manager`, `employee`, or `customer`. "
        "Admin / researcher roles must be granted by an administrator."
    ),
)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    existing = await get_user_by_email(db, body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    user = await create_user(
        db,
        name=body.name,
        email=body.email,
        hashed_password=hash_password(body.password),
        role=body.role,
        department=body.department,
    )
    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive a JWT",
    description="Returns the same 401 for wrong email OR wrong password to prevent user-enumeration.",
)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    _INVALID = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = await get_user_by_email(db, body.email)
    if user is None or not verify_password(body.password, user.hashed_password):
        raise _INVALID
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact the research team.",
        )
    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


# ── Me ────────────────────────────────────────────────────────────────────────

@auth_router.get(
    "/me",
    response_model=UserOut,
    summary="Return the currently authenticated user",
)
async def me(current_user: UserOrm = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout — client-side token invalidation",
    description="JWTs are stateless. The client must delete the token from storage.",
)
async def logout() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Admin: list users ─────────────────────────────────────────────────────────

@auth_router.get(
    "/users",
    response_model=list[UserOut],
    summary="[Admin] List all users",
    description="Returns all registered users. Restricted to admin and researcher roles.",
)
async def admin_list_users(
    _actor: UserOrm = Depends(require_roles("admin", "researcher")),
    db: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    users = await list_users(db)
    return [UserOut.model_validate(u) for u in users]


# ── Admin: set role ───────────────────────────────────────────────────────────

@auth_router.patch(
    "/users/{user_id}/role",
    response_model=UserOut,
    summary="[Admin] Assign a role to a user",
    description=(
        "Allows an admin to assign any role including `admin` and `researcher`. "
        "An admin cannot change their own role (self-lockout prevention)."
    ),
)
async def admin_set_role(
    user_id: str,
    body: SetRoleRequest,
    actor: UserOrm = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    if actor.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot change their own role to prevent accidental lockout.",
        )
    target = await get_user_by_id(db, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    updated = await set_user_role(db, target, body.role)
    return UserOut.model_validate(updated)


# ── Admin: activate / deactivate ─────────────────────────────────────────────

@auth_router.patch(
    "/users/{user_id}/active",
    response_model=UserOut,
    summary="[Admin] Activate or deactivate a user account",
)
async def admin_set_active(
    user_id: str,
    body: SetActiveRequest,
    actor: UserOrm = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    if actor.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot deactivate their own account.",
        )
    target = await get_user_by_id(db, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    updated = await set_user_active(db, target, active=body.is_active)
    return UserOut.model_validate(updated)
