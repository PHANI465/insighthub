"""
backend/app/core/config.py

Centralised settings for the InsightHub FastAPI backend.
Reads every value from environment variables — nothing is hardcoded.

Priority order for secret resolution
──────────────────────────────────────
  1. Azure Key Vault (when AZURE_KEYVAULT_URL is set and accessible)
  2. Environment variable (always works; used for local dev and CI)

BaseSettings automatically reads from the .env file via python-dotenv
if the file is present in the working directory.
"""

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),  # works whether CWD is backend/ or project root
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Azure SQL ──────────────────────────────────────────────────────────────
    db_server:   str = ""
    db_name:     str = ""
    db_user:     str = ""
    db_password: str = ""
    db_port:     int = 1433

    # ── Azure Key Vault ────────────────────────────────────────────────────────
    azure_keyvault_url: Optional[str] = None

    # ── Azure AI Search ────────────────────────────────────────────────────────
    azure_search_endpoint: str = ""
    azure_search_key:      str = ""
    azure_search_index:    str = "insighthub-docs"

    # ── Azure OpenAI ───────────────────────────────────────────────────────────
    azure_openai_endpoint:   str = ""
    azure_openai_key:        str = ""
    azure_openai_deployment: str = "gpt-4o"

    # ── Power BI ───────────────────────────────────────────────────────────────
    powerbi_client_id:     str = ""
    powerbi_client_secret: str = ""
    powerbi_tenant_id:     str = ""
    powerbi_workspace_id:  str = ""
    powerbi_report_id:     str = ""

    # ── JWT ────────────────────────────────────────────────────────────────────
    jwt_secret_key:      str = ""
    jwt_algorithm:       str = "HS256"
    jwt_access_token_expire_minutes:  int = 60
    jwt_refresh_token_expire_minutes: int = 10080  # 7 days

    # ── Application ────────────────────────────────────────────────────────────
    app_name:     str = "InsightHub API"
    app_version:  str = "1.0.0"
    debug:        bool = False
    allowed_origins: str = "http://localhost:3000"

    # ── Application Insights ───────────────────────────────────────────────────
    applicationinsights_connection_string: Optional[str] = None

    @field_validator("db_server", "db_name", "db_user", "db_password", mode="before")
    @classmethod
    def must_not_be_empty(cls, v: str, info) -> str:
        if not v:
            raise ValueError(
                f"Required setting '{info.field_name}' is not set. "
                f"Add it to your .env file."
            )
        return v

    def get_cors_origins(self) -> List[str]:
        """Parse comma-separated ALLOWED_ORIGINS into a list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def get_odbc_connection_string(self) -> str:
        """
        Build the pyodbc connection string.
        This string contains the password — never log it.
        """
        return (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={self.db_server},{self.db_port};"
            f"DATABASE={self.db_name};"
            f"UID={self.db_user};"
            f"PWD={self.db_password};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout=30;"
        )


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings instance.
    The @lru_cache ensures settings are loaded once at startup,
    not on every request.  Call invalidate_settings_cache() in tests.
    """
    return Settings()


def invalidate_settings_cache() -> None:
    """Clear the settings cache (use in tests only)."""
    get_settings.cache_clear()
