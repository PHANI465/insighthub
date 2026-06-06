"""
etl-pipelines/python-local/db_connection.py

Database connection management for the InsightHub ETL pipeline.
Provides a context manager that opens one pyodbc connection, yields it,
commits/rolls back, and always closes — even if an exception escapes.

Why one connection per ETL run?
────────────────────────────────
All dimension loads and fact loads share one connection so that temp tables
(#staging_*) created in one function are visible to MERGE statements in the
same function.  Azure SQL temp tables are scoped to the connection, not the
session, so a second connection would not see them.
"""

import logging
from contextlib import contextmanager
from typing import Generator

import pyodbc

from config import DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT

log = logging.getLogger(__name__)


def _build_conn_string() -> str:
    """
    Assemble the ODBC connection string from env vars.
    This function is intentionally private — the string contains the password
    and must never be logged or stored anywhere outside this module.
    """
    return (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={DB_SERVER},{DB_PORT};"
        f"DATABASE={DB_NAME};"
        f"UID={DB_USER};"
        f"PWD={DB_PASSWORD};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=yes;"
        f"Connection Timeout=60;"
        f"Login Timeout=30;"
    )


@contextmanager
def get_connection() -> Generator[pyodbc.Connection, None, None]:
    """
    Context manager: opens a pyodbc connection with autocommit=False,
    yields it, and guarantees closure in the finally block.

    The caller is responsible for conn.commit() after each successful table load.
    On exception, callers should call conn.rollback() before re-raising.

    Usage:
        with get_connection() as conn:
            load_dim_customer(conn, df)
            load_fact_sales(conn, df)
    """
    conn: pyodbc.Connection | None = None
    try:
        conn = pyodbc.connect(_build_conn_string(), autocommit=False)
        log.debug("Azure SQL connection opened (%s / %s)", DB_SERVER, DB_NAME)
        yield conn
    except pyodbc.Error as exc:
        # Only log the ODBC state code — never the connection string
        state = exc.args[0] if exc.args else "UNKNOWN"
        raise ConnectionError(
            f"Cannot connect to Azure SQL ({DB_SERVER}/{DB_NAME}). "
            f"ODBC state: {state}. "
            f"Verify DB_SERVER, DB_USER, DB_PASSWORD in .env."
        ) from exc
    finally:
        if conn is not None:
            conn.close()
            log.debug("Azure SQL connection closed.")


def test_connection() -> bool:
    """
    Quick smoke-test — connects, runs SELECT 1, returns True on success.
    Used by etl_runner.py --test-connection before starting the full pipeline.
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 AS ping")
            result = cursor.fetchone()
            cursor.close()
            return result is not None and result[0] == 1
    except ConnectionError:
        return False
