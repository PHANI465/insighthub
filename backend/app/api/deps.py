"""
backend/app/api/deps.py

FastAPI dependency injection functions shared across all route modules.

Current user flow
──────────────────
  1. Client sends: Authorization: Bearer <access_token>
  2. get_current_user() decodes the JWT and returns a UserInfo dict
  3. require_role("Analyst") returns a dependency that raises 403 if
     the user's role is insufficient

Database flow
─────────────
  Routes declare `conn: pyodbc.Connection = Depends(get_db_conn)`
  and receive an open connection that is automatically closed after
  the request finishes (via the context manager in core/database.py).
"""

from typing import Generator

import pyodbc
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.core.database import get_db
from app.core.security import decode_access_token, role_has_access
from app.models.schemas import UserInfo

# Bearer token extractor — raises 403 (not 401) if header is missing
_bearer = HTTPBearer(auto_error=True)


def get_db_conn() -> Generator[pyodbc.Connection, None, None]:
    """
    FastAPI dependency: yields an open pyodbc connection.
    The connection is closed automatically when the request finishes.
    """
    with get_db() as conn:
        yield conn


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> UserInfo:
    """
    FastAPI dependency: decode the Bearer JWT and return the current user.
    Raises HTTP 401 if the token is missing, expired, or tampered with.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
        username: str = payload.get("sub")
        user_id:  int = payload.get("uid")
        role:     str = payload.get("role")
        if not username or not role:
            raise credentials_exception
        return UserInfo(
            user_id=user_id,
            username=username,
            email="",      # Not in token — fetch from DB if needed
            role=role,
            is_active=True,
        )
    except JWTError:
        raise credentials_exception


def require_role(minimum_role: str):
    """
    Factory that returns a FastAPI dependency enforcing a minimum role.

    Usage:
        @router.get("/admin-only")
        def admin_endpoint(
            user: UserInfo = Depends(require_role("Admin"))
        ):
            ...
    """
    def _check_role(current_user: UserInfo = Depends(get_current_user)) -> UserInfo:
        if not role_has_access(current_user.role, minimum_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{minimum_role}' or higher is required. "
                       f"Your role: '{current_user.role}'.",
            )
        return current_user
    return _check_role
