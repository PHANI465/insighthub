"""
backend/app/core/security.py

JWT creation, validation, and password hashing for InsightHub.

Token structure
───────────────
Access token (short-lived, 60 min default):
  {
    "sub":  "username",
    "role": "Admin | Analyst | Viewer",
    "uid":  user_id (int),
    "exp":  unix timestamp,
    "type": "access"
  }

Refresh token (long-lived, 7 days default):
  {
    "sub":  "username",
    "exp":  unix timestamp,
    "type": "refresh"
  }

RBAC roles (least-privilege order)
────────────────────────────────────
  Viewer   → read dashboard and embedded reports only
  Analyst  → Viewer + metrics API + search + insights
  Admin    → Analyst + user management + insight generation trigger
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

# bcrypt password context — AUTO_DEPRECATED handles schema upgrades automatically
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ROLES = {"Admin", "Analyst", "Viewer"}
ROLE_HIERARCHY = {"Admin": 3, "Analyst": 2, "Viewer": 1}


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Return a bcrypt hash of `plain`."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if `plain` matches the stored `hashed` bcrypt value."""
    return _pwd_context.verify(plain, hashed)


# ── Token helpers ─────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def create_access_token(
    username: str,
    user_id: int,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.

    Parameters
    ----------
    username      : subject claim
    user_id       : numeric user ID stored in 'uid' claim
    role          : RBAC role ('Admin', 'Analyst', 'Viewer')
    expires_delta : override the default expiry from settings
    """
    if role not in ROLES:
        raise ValueError(f"Invalid role '{role}'. Must be one of: {ROLES}")

    delta = expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub":  username,
        "uid":  user_id,
        "role": role,
        "exp":  _now_utc() + delta,
        "iat":  _now_utc(),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(username: str) -> str:
    """Create a long-lived refresh token (no role claim — must re-authenticate)."""
    payload = {
        "sub":  username,
        "exp":  _now_utc() + timedelta(minutes=settings.jwt_refresh_token_expire_minutes),
        "iat":  _now_utc(),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.

    Returns the decoded payload dict.
    Raises jose.JWTError on invalid/expired tokens — the caller
    (FastAPI dependency) translates this to HTTP 401.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != "access":
        raise JWTError("Token is not an access token")
    return payload


def decode_refresh_token(token: str) -> dict:
    """Decode and validate a refresh token. Raises JWTError on failure."""
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != "refresh":
        raise JWTError("Token is not a refresh token")
    return payload


def role_has_access(user_role: str, required_role: str) -> bool:
    """
    Return True if user_role meets or exceeds required_role.
    Example: role_has_access('Admin', 'Analyst') → True
             role_has_access('Viewer', 'Analyst') → False
    """
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 999)
