"""
JWT helper utilities: token creation and verification.
Keeps security logic separate from the HTTP layer.

Password hashing uses bcrypt directly (bypassing passlib which is
incompatible with bcrypt>=4.x on Python 3.12+).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt  # noqa: F401 (JWTError re-exported for callers)

from app.core.config import get_settings

settings = get_settings()


# ── Password hashing (bcrypt direct) ─────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain* as a UTF-8 string."""
    # Truncate to 72 bytes — bcrypt hard limit
    raw = plain.encode("utf-8")[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the bcrypt *hashed* value."""
    raw = plain.encode("utf-8")[:72]
    return bcrypt.checkpw(raw, hashed.encode("utf-8"))


# ── JWT ───────────────────────────────────────────────────────────────────────
ALGORITHM = "HS256"


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Encode *data* as a signed JWT. Expiry defaults to settings value."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and verify *token*.
    Raises JWTError on any failure (expired, invalid signature, malformed).
    """
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
