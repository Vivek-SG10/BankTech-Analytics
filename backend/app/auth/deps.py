"""
FastAPI dependencies for authentication and authorisation.

get_current_user   — validates Bearer JWT, returns the authenticated UserOrm.
get_current_user_optional — same but returns None for unauthenticated callers.
require_roles(*roles) — synchronous factory; returns a Depends-compatible
                        callable that checks the authenticated user's role.

Usage
-----
# Require a valid JWT (any role):
@router.get("/me")
async def me(user: UserOrm = Depends(get_current_user)):
    ...

# Require admin or researcher:
@router.get("/admin-only", dependencies=[Depends(require_roles("admin", "researcher"))])
async def admin_view():
    ...

# Capture the user object AND enforce role:
@router.patch("/users/{uid}/role")
async def set_role(uid: str, actor: UserOrm = Depends(require_roles("admin"))):
    ...
"""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.crud import get_user_by_id
from app.auth.models import UserOrm
from app.auth.security import decode_access_token
from app.core.database import get_db

# auto_error=False so we can return None for optional auth
_bearer_required = HTTPBearer(auto_error=True)
_bearer_optional = HTTPBearer(auto_error=False)


# ── Core dependency ────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_required),
    db: AsyncSession = Depends(get_db),
) -> UserOrm:
    """
    Validate the Bearer JWT and return the matching active UserOrm.
    Raises 401 for invalid/expired tokens; 403 for deactivated accounts.
    """
    _creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise _creds_exc
    except JWTError:
        raise _creds_exc

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise _creds_exc
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact the research team.",
        )
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
    db: AsyncSession = Depends(get_db),
) -> UserOrm | None:
    """Same as get_current_user but returns None instead of raising for missing tokens."""
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            return None
        user = await get_user_by_id(db, user_id)
        return user if (user and user.is_active) else None
    except JWTError:
        return None


# ── Role-enforcement factory ───────────────────────────────────────────────────

def require_roles(*roles: str) -> Callable[..., UserOrm]:
    """
    Synchronous factory — returns a FastAPI dependency callable that enforces
    the given roles. The returned callable also resolves get_current_user so
    callers get the UserOrm back directly.

    Unlike an async factory, this works correctly with Depends() because the
    *returned* inner function is what FastAPI calls, not the factory itself.

    Example
    -------
    Depends(require_roles("admin", "researcher"))
    """
    async def _enforce(user: UserOrm = Depends(get_current_user)) -> UserOrm:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This endpoint requires one of the following roles: "
                    f"{', '.join(roles)}. Your role is '{user.role}'."
                ),
            )
        return user

    return _enforce
