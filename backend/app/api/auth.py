"""
backend/app/api/auth.py

Authentication routes:
  POST /api/auth/token    — login with username + password, returns JWT pair
  POST /api/auth/refresh  — exchange a refresh token for a new access token
  GET  /api/auth/me       — return current authenticated user's profile
"""

import logging

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError

from app.api.deps import get_current_user, get_db_conn
from app.core.appinsights import track_event, track_failed_login
from app.core.security import create_access_token, decode_refresh_token
from app.models.schemas import LoginRequest, RefreshRequest, TokenResponse, UserInfo
from app.services.auth_service import (
    authenticate_user,
    create_tokens_for_user,
    get_user_by_username,
    record_login,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Login and get JWT tokens",
    description=(
        "Authenticate with username and password. "
        "Returns an access token (60 min) and a refresh token (7 days). "
        "Include the access token as: `Authorization: Bearer <token>`"
    ),
)
def login(
    body: LoginRequest,
    conn: pyodbc.Connection = Depends(get_db_conn),
) -> TokenResponse:
    """
    Authenticate a user and return JWT tokens.

    OWASP A07 — Identification and Authentication Failures:
    • Password verified via bcrypt (constant-time comparison)
    • Timing-safe: always runs bcrypt.verify regardless of whether user exists
    • Does not reveal whether username or password is wrong ("Invalid credentials")
    • Login event tracked for audit (no password in telemetry)
    """
    user = authenticate_user(conn, body.username, body.password)
    if not user:
        # Log server-side with username for operator visibility; App Insights event
        # intentionally omits username to prevent log-based account enumeration.
        log.warning("Failed login attempt for username: %s", body.username)
        track_failed_login(reason="invalid_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    record_login(conn, body.username)
    track_event("UserLogin", {"username": body.username, "role": user["role"]})
    log.info("Successful login: %s (role=%s)", body.username, user["role"])
    return create_tokens_for_user(user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh an expired access token",
)
def refresh_token(
    body: RefreshRequest,
    conn: pyodbc.Connection = Depends(get_db_conn),
) -> TokenResponse:
    """Exchange a valid refresh token for a new access token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_refresh_token(body.refresh_token)
        username: str = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user_by_username(conn, username)
    if not user or not user.is_active:
        raise credentials_exception

    # Re-fetch user dict with password hash for token creation
    from app.core.database import execute_query
    rows = execute_query(
        conn,
        "SELECT UserID, Username, Email, PasswordHash, Role, IsActive FROM dbo.AppUsers WHERE Username = ?",
        (username,),
        fetch="all",
    )
    if not rows:
        raise credentials_exception

    user_dict = {
        "user_id": rows[0][0],
        "username": rows[0][1],
        "email": rows[0][2],
        "password_hash": rows[0][3],
        "role": rows[0][4],
        "is_active": bool(rows[0][5]),
    }
    return create_tokens_for_user(user_dict)


@router.get(
    "/me",
    response_model=UserInfo,
    summary="Get current user profile",
)
def get_me(current_user: UserInfo = Depends(get_current_user)) -> UserInfo:
    """Return the authenticated user's profile from the JWT claims."""
    return current_user
