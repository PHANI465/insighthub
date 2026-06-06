"""
database/seed_users.py

Creates three demo users in dbo.AppUsers with bcrypt-hashed passwords.
Run this ONCE after deploying 06_app_users.sql.

Demo credentials (change in production!)
──────────────────────────────────────────
  Admin:    admin / InsightHub@Admin2024!
  Analyst:  analyst / InsightHub@Analyst2024!
  Viewer:   viewer / InsightHub@Viewer2024!

Usage
─────
  python database/seed_users.py
  python database/seed_users.py --force    # overwrite existing users
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import pyodbc
from dotenv import load_dotenv
from passlib.context import CryptContext

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEMO_USERS = [
    {
        "username": "admin",
        "email":    "admin@insighthub.com",
        "password": "InsightHub@Admin2024!",
        "role":     "Admin",
    },
    {
        "username": "analyst",
        "email":    "analyst@insighthub.com",
        "password": "InsightHub@Analyst2024!",
        "role":     "Analyst",
    },
    {
        "username": "viewer",
        "email":    "viewer@insighthub.com",
        "password": "InsightHub@Viewer2024!",
        "role":     "Viewer",
    },
]


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Required environment variable '{name}' is not set.")
    return value


def _build_conn_str() -> str:
    server   = _require_env("DB_SERVER")
    db       = _require_env("DB_NAME")
    user     = _require_env("DB_USER")
    password = _require_env("DB_PASSWORD")
    port     = os.getenv("DB_PORT", "1433")
    return (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server},{port};"
        f"DATABASE={db};"
        f"UID={user};"
        f"PWD={password};"
        f"Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=30;"
    )


def seed_users(force: bool = False) -> None:
    log.info("Connecting to Azure SQL …")
    conn = pyodbc.connect(_build_conn_str(), autocommit=True)
    cursor = conn.cursor()

    for user in DEMO_USERS:
        # Check if user already exists
        cursor.execute(
            "SELECT COUNT(*) FROM dbo.AppUsers WHERE Username = ?",
            (user["username"],)
        )
        exists = cursor.fetchone()[0] > 0

        if exists and not force:
            log.info("  – User '%s' already exists — skipping (use --force to overwrite)", user["username"])
            continue

        hashed = _pwd.hash(user["password"])

        if exists and force:
            cursor.execute(
                """UPDATE dbo.AppUsers
                   SET Email = ?, PasswordHash = ?, Role = ?, IsActive = 1
                   WHERE Username = ?""",
                (user["email"], hashed, user["role"], user["username"]),
            )
            log.info("  ✓ Updated user '%s' (role=%s)", user["username"], user["role"])
        else:
            cursor.execute(
                """INSERT INTO dbo.AppUsers (Username, Email, PasswordHash, Role)
                   VALUES (?, ?, ?, ?)""",
                (user["username"], user["email"], hashed, user["role"]),
            )
            log.info("  ✓ Created user '%s' (role=%s)", user["username"], user["role"])

    cursor.close()
    conn.close()
    log.info("Seed complete.")
    log.info("")
    log.info("Demo credentials:")
    for u in DEMO_USERS:
        log.info("  %-10s  password: %s", u["username"], u["password"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed InsightHub demo users")
    parser.add_argument("--force", action="store_true", help="Overwrite existing users")
    args = parser.parse_args()
    try:
        seed_users(force=args.force)
    except Exception as exc:
        log.error("Seed failed: %s", exc)
        sys.exit(1)
