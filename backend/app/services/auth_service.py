"""
backend/app/services/auth_service.py

Authentication business logic — user lookup, password verification,
token creation.  Queries dbo.AppUsers in Azure SQL.
"""

import logging
from typing import Optional

import pyodbc

from app.core.config import get_settings
from app.core.database import execute_query
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
)
from app.models.schemas import TokenResponse, UserInfo

log = logging.getLogger(__name__)
settings = get_settings()

_SELECT_USER_BY_USERNAME = """
SELECT UserID, Username, Email, PasswordHash, Role, IsActive
FROM   dbo.AppUsers
WHERE  Username = ?
"""

_UPDATE_LAST_LOGIN = """
UPDATE dbo.AppUsers
SET    LastLoginDate = SYSUTCDATETIME()
WHERE  Username = ?
"""


def _row_to_user(row) -> Optional[dict]:
    if row is None:
        return None
    return {
        "user_id":       row[0],
        "username":      row[1],
        "email":         row[2],
        "password_hash": row[3],
        "role":          row[4],
        "is_active":     bool(row[5]),
    }


def authenticate_user(
    conn: pyodbc.Connection,
    username: str,
    password: str,
) -> Optional[dict]:
    """
    Look up a user by username and verify the bcrypt password.
    Returns the user dict if valid, None if credentials are wrong.

    Security notes:
    - Uses parameterised query (? placeholder) — no SQL injection risk.
    - Password is verified client-side via bcrypt — hash is never returned to API.
    - Timing-safe: bcrypt.verify always runs (no early exit on wrong username)
      to prevent timing-based user enumeration.
    """
    rows = execute_query(conn, _SELECT_USER_BY_USERNAME, (username,), fetch="all")
    user = _row_to_user(rows[0] if rows else None)

    # Always call verify_password even if user not found — prevents timing attacks
    stored_hash = user["password_hash"] if user else "$2b$12$invalid_hash_for_timing_safety"
    password_ok = verify_password(password, stored_hash)

    if user is None or not password_ok or not user["is_active"]:
        return None

    return user


def create_tokens_for_user(user: dict) -> TokenResponse:
    """
    Generate access + refresh tokens for an authenticated user.
    """
    access_token = create_access_token(
        username=user["username"],
        user_id=user["user_id"],
        role=user["role"],
    )
    refresh_token = create_refresh_token(username=user["username"])

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        role=user["role"],
    )


def record_login(conn: pyodbc.Connection, username: str) -> None:
    """Update LastLoginDate for audit trail. Swallows errors — login must succeed."""
    try:
        cursor = conn.cursor()
        cursor.execute(_UPDATE_LAST_LOGIN, (username,))
        conn.commit()
        cursor.close()
    except pyodbc.Error as exc:
        log.warning("Could not update LastLoginDate for %s: %s", username, exc)


def get_user_by_username(
    conn: pyodbc.Connection,
    username: str,
) -> Optional[UserInfo]:
    """Fetch public user info (no password hash) by username."""
    rows = execute_query(conn, _SELECT_USER_BY_USERNAME, (username,), fetch="all")
    user = _row_to_user(rows[0] if rows else None)
    if not user:
        return None
    return UserInfo(
        user_id=user["user_id"],
        username=user["username"],
        email=user["email"],
        role=user["role"],
        is_active=user["is_active"],
    )
