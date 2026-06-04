"""
database/run_schema.py

Python runner for deploying the InsightHub star schema to Azure SQL Database.
Reads all SQL files from database/schema/ in execution order and runs them
against the Azure SQL instance configured in environment variables.

Usage
-----
  # Deploy full schema
  python database/run_schema.py

  # Verify schema (check tables/views exist without deploying)
  python database/run_schema.py --verify

  # Deploy a single file
  python database/run_schema.py --file database/schema/04_indexes.sql

Why Python instead of sqlcmd?
──────────────────────────────
  • Azure DevOps / GitHub Actions CI environments may not have sqlcmd installed.
  • Python can read credentials from Azure Key Vault (Phase 9).
  • Structured logging and error reporting are easier to implement.
  • The `:r` file-include directive in run_all.sql is sqlcmd-only; Python
    handles the file sequencing explicitly instead.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

# ── Load environment ──────────────────────────────────────────────────────────
load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Environment validation ────────────────────────────────────────────────────
def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(
            f"Required environment variable '{name}' is not set. "
            f"Copy .env.example → .env and fill in the value."
        )
    return value

DB_SERVER   = _require_env("DB_SERVER")
DB_NAME     = _require_env("DB_NAME")
DB_USER     = _require_env("DB_USER")
DB_PASSWORD = _require_env("DB_PASSWORD")
DB_PORT     = int(os.getenv("DB_PORT", "1433"))

# ── Schema files in exact execution order ────────────────────────────────────
SCHEMA_DIR = Path(__file__).parent / "schema"

ORDERED_FILES = [
    SCHEMA_DIR / "01_dimensions.sql",
    SCHEMA_DIR / "02_facts.sql",
    SCHEMA_DIR / "03_populate_dim_date.sql",
    SCHEMA_DIR / "04_indexes.sql",
    SCHEMA_DIR / "05_views.sql",
]

# Tables and views to verify after deployment
EXPECTED_TABLES = [
    "DimDate", "DimGeography", "DimCustomer",
    "DimProduct", "DimEmployee", "DimCampaign",
    "FactSales", "FactSupportTickets", "FactCampaignPerformance",
]
EXPECTED_VIEWS = [
    "vw_SalesSummary", "vw_CustomerAnalytics", "vw_ProductPerformance",
    "vw_SupportMetrics", "vw_CampaignROI",
]

# ── Database connection ───────────────────────────────────────────────────────
def build_connection_string() -> str:
    """
    Build the pyodbc connection string from individual environment variables.
    Uses the Microsoft ODBC Driver 18 for SQL Server (Azure SQL recommended).
    Never logs or prints this string — it contains the password.
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
    )


def get_connection() -> pyodbc.Connection:
    """Open and return an Azure SQL connection. Raises on failure."""
    conn_str = build_connection_string()
    try:
        conn = pyodbc.connect(conn_str, autocommit=False)
        return conn
    except pyodbc.Error as exc:
        # Log the error code only — never log the full connection string
        raise ConnectionError(
            f"Could not connect to Azure SQL ({DB_SERVER}/{DB_NAME}). "
            f"ODBC error: {exc.args[0] if exc.args else 'unknown'}. "
            f"Check DB_SERVER, DB_USER, DB_PASSWORD in your .env file."
        ) from exc


# ── SQL execution helpers ─────────────────────────────────────────────────────
def split_batches(sql: str) -> list[str]:
    """
    Split a T-SQL script on GO batch separators (case-insensitive, own line).
    Returns a list of non-empty batch strings.
    """
    batches = []
    current: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip().upper()
        if stripped == "GO":
            batch = "\n".join(current).strip()
            if batch:
                batches.append(batch)
            current = []
        else:
            current.append(line)
    # Append the last batch if no trailing GO
    batch = "\n".join(current).strip()
    if batch:
        batches.append(batch)
    return batches


def execute_file(conn: pyodbc.Connection, filepath: Path) -> None:
    """
    Read a SQL file, split it on GO, and execute each batch in a transaction.
    Rolls back the entire file on any error so the database stays consistent.
    """
    if not filepath.exists():
        raise FileNotFoundError(f"SQL file not found: {filepath}")

    log.info("Executing: %s", filepath.name)
    sql = filepath.read_text(encoding="utf-8")
    batches = split_batches(sql)

    cursor = conn.cursor()
    try:
        for i, batch in enumerate(batches, start=1):
            if not batch.strip():
                continue
            try:
                cursor.execute(batch)
                # PRINT statements from T-SQL come back as messages
                while cursor.nextset():
                    pass
            except pyodbc.Error as exc:
                conn.rollback()
                raise RuntimeError(
                    f"Error in batch {i} of {filepath.name}: {exc}"
                ) from exc
        conn.commit()
        log.info("  ✓ %s — committed (%d batches)", filepath.name, len(batches))
    finally:
        cursor.close()


# ── Verification ──────────────────────────────────────────────────────────────
def verify_schema(conn: pyodbc.Connection) -> bool:
    """
    Check that all expected tables and views exist in the database.
    Returns True if everything is present; False otherwise.
    """
    cursor = conn.cursor()
    all_ok = True

    log.info("── Schema verification ──")

    for table in EXPECTED_TABLES:
        cursor.execute(
            "SELECT COUNT(1) FROM sys.tables "
            "WHERE name = ? AND schema_id = SCHEMA_ID('dbo')",
            (table,)
        )
        exists = cursor.fetchone()[0] == 1
        status = "✓" if exists else "✗ MISSING"
        log.info("  %s Table: dbo.%s", status, table)
        if not exists:
            all_ok = False

    for view in EXPECTED_VIEWS:
        cursor.execute(
            "SELECT COUNT(1) FROM sys.views "
            "WHERE name = ? AND schema_id = SCHEMA_ID('dbo')",
            (view,)
        )
        exists = cursor.fetchone()[0] == 1
        status = "✓" if exists else "✗ MISSING"
        log.info("  %s View : dbo.%s", status, view)
        if not exists:
            all_ok = False

    # Report row count in DimDate as a sanity check
    cursor.execute("SELECT COUNT(1) FROM dbo.DimDate")
    row_count = cursor.fetchone()[0]
    log.info("  DimDate rows: %d (expected ~4,749)", row_count)

    cursor.close()
    return all_ok


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy or verify the InsightHub Azure SQL schema"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify existing schema without deploying anything",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Deploy a single SQL file instead of the full schema",
    )
    args = parser.parse_args()

    log.info("══════════════════════════════════════════════════════")
    log.info("InsightHub — Azure SQL Schema Runner")
    log.info("  Server  : %s", DB_SERVER)
    log.info("  Database: %s", DB_NAME)
    log.info("══════════════════════════════════════════════════════")

    try:
        conn = get_connection()
        log.info("Connected to Azure SQL ✓")
    except ConnectionError as exc:
        log.error("%s", exc)
        sys.exit(1)

    try:
        if args.verify:
            ok = verify_schema(conn)
            if ok:
                log.info("✅  All schema objects verified successfully.")
            else:
                log.error("⚠️  Some schema objects are missing. Run without --verify to deploy.")
                sys.exit(1)

        elif args.file:
            target = Path(args.file)
            execute_file(conn, target)
            log.info("✅  File deployed successfully.")

        else:
            # Full schema deployment
            for i, sql_file in enumerate(ORDERED_FILES, start=1):
                log.info("[ %d/%d ] %s", i, len(ORDERED_FILES), sql_file.name)
                execute_file(conn, sql_file)

            log.info("══════════════════════════════════════════════════════")
            log.info("✅  Full schema deployed. Running verification …")
            log.info("══════════════════════════════════════════════════════")
            ok = verify_schema(conn)
            if ok:
                log.info("✅  All objects verified. Schema deployment complete.")
            else:
                log.error("⚠️  Deployment completed with missing objects — review logs.")
                sys.exit(1)

    except (RuntimeError, FileNotFoundError) as exc:
        log.error("Deployment failed: %s", exc)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
