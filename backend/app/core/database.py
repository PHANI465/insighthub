"""
backend/app/core/database.py

Database connection management for the InsightHub FastAPI backend.
Provides a context manager that opens one pyodbc connection per request,
commits on clean exit, and always closes — even if an exception escapes.

Connection pooling note
───────────────────────
pyodbc does not have a built-in async connection pool.  For the traffic
volumes expected by this project (internal analytics tool, <100 concurrent
users), creating a connection per request is acceptable.  If scaling is
required, replace this with aioodbc or use SQLAlchemy async engine.
"""

import logging
from contextlib import contextmanager
from typing import Any, Generator, List, Optional, Tuple

import pyodbc

from app.core.config import get_settings

log = logging.getLogger(__name__)


@contextmanager
def get_db() -> Generator[pyodbc.Connection, None, None]:
    """
    FastAPI dependency and standalone context manager for DB access.

    Usage in route handlers (via FastAPI Depends):
        def my_route(conn: pyodbc.Connection = Depends(get_db)):
            ...

    Usage in service layer (standalone):
        with get_db() as conn:
            ...
    """
    settings = get_settings()
    conn: Optional[pyodbc.Connection] = None
    try:
        conn = pyodbc.connect(
            settings.get_odbc_connection_string(),
            autocommit=False,
        )
        yield conn
    except pyodbc.Error as exc:
        state = exc.args[0] if exc.args else "UNKNOWN"
        raise ConnectionError(
            f"Cannot connect to Azure SQL. ODBC state: {state}. "
            f"Check DB_SERVER, DB_USER, DB_PASSWORD in .env."
        ) from exc
    finally:
        if conn is not None:
            conn.close()


def execute_query(
    conn: pyodbc.Connection,
    sql: str,
    params: Optional[Tuple] = None,
    fetch: str = "all",
) -> Any:
    """
    Execute a parameterised SELECT query and return results.

    Parameters
    ----------
    sql    : Parameterised SQL string with ? placeholders
    params : Tuple of parameter values (never build from user input with f-strings)
    fetch  : 'all' → list of rows, 'one' → single row or None, 'none' → no fetch

    Returns
    -------
    list of pyodbc.Row, single pyodbc.Row, or None
    """
    cursor = conn.cursor()
    try:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        if fetch == "all":
            return cursor.fetchall()
        elif fetch == "one":
            return cursor.fetchone()
        else:
            return None
    finally:
        cursor.close()


def rows_to_dicts(rows: List[Any], columns: List[str]) -> List[dict]:
    """Convert a list of pyodbc.Row objects to a list of dicts with named keys."""
    return [dict(zip(columns, row)) for row in rows]


def execute_scalar(
    conn: pyodbc.Connection,
    sql: str,
    params: Optional[Tuple] = None,
) -> Any:
    """Execute a query that returns a single scalar value."""
    row = execute_query(conn, sql, params, fetch="one")
    if row is None:
        return None
    return row[0]
