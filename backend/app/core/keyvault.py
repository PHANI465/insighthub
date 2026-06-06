"""
backend/app/core/keyvault.py

Azure Key Vault secret retrieval for the InsightHub backend.

How it works
────────────
At app startup, if AZURE_KEYVAULT_URL is set, the backend fetches secrets
from Key Vault and OVERRIDES the corresponding environment variables.
This means secrets are stored in Key Vault (not .env) in production,
but the rest of the codebase reads them from settings as usual.

Authentication
──────────────
Uses DefaultAzureCredential which tries (in order):
  1. EnvironmentCredential   — AZURE_CLIENT_ID + AZURE_CLIENT_SECRET + AZURE_TENANT_ID
  2. WorkloadIdentityCredential — AKS pod identity
  3. ManagedIdentityCredential  — Azure App Service managed identity (production)
  4. AzureCliCredential          — local developer CLI login
  5. AzurePowerShellCredential   — local PS login

In production (App Service with managed identity enabled), option 3 activates
automatically — no credentials need to be configured in the environment.

Key Vault secret names → Settings field names
──────────────────────────────────────────────
  insighthub-db-password            → db_password
  insighthub-db-user                → db_user
  insighthub-jwt-secret             → jwt_secret_key
  insighthub-openai-key             → azure_openai_key
  insighthub-search-key             → azure_search_key
  insighthub-powerbi-client-secret  → powerbi_client_secret
"""

import logging
import os
from functools import lru_cache
from typing import Optional

log = logging.getLogger(__name__)

# Map: Key Vault secret name → environment variable name
_KV_SECRET_MAP = {
    "insighthub-db-password":           "DB_PASSWORD",
    "insighthub-db-user":               "DB_USER",
    "insighthub-jwt-secret":            "JWT_SECRET_KEY",
    "insighthub-openai-key":            "AZURE_OPENAI_KEY",
    "insighthub-search-key":            "AZURE_SEARCH_KEY",
    "insighthub-powerbi-client-secret": "POWERBI_CLIENT_SECRET",
}


def load_keyvault_secrets(vault_url: Optional[str] = None) -> dict:
    """
    Fetch all mapped secrets from Azure Key Vault.
    Returns a dict of {env_var_name: secret_value}.
    Returns an empty dict if vault_url is not set (local dev without Key Vault).

    Silently skips secrets that don't exist in the vault (not all are required
    in every deployment environment).
    """
    if not vault_url:
        log.info("AZURE_KEYVAULT_URL not set — skipping Key Vault secret loading.")
        return {}

    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        from azure.core.exceptions import ResourceNotFoundError

        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)
        loaded: dict = {}

        for secret_name, env_var in _KV_SECRET_MAP.items():
            try:
                secret = client.get_secret(secret_name)
                loaded[env_var] = secret.value
                log.info("  ✓ Loaded secret: %s", secret_name)
            except ResourceNotFoundError:
                log.debug("  Secret '%s' not found in Key Vault — using env var.", secret_name)
            except Exception as exc:
                log.warning("  Could not load '%s' from Key Vault: %s", secret_name, exc)

        return loaded

    except ImportError:
        log.warning(
            "azure-keyvault-secrets or azure-identity not installed. "
            "Skipping Key Vault integration."
        )
        return {}
    except Exception as exc:
        log.warning(
            "Key Vault connection failed (%s). "
            "Falling back to environment variables for all secrets.",
            exc,
        )
        return {}


def inject_keyvault_secrets_into_env(vault_url: Optional[str] = None) -> None:
    """
    Fetch secrets from Key Vault and inject them into os.environ.
    Call this ONCE at application startup, before Settings() is instantiated.

    This allows the rest of the application to read secrets via os.getenv()
    and pydantic Settings without knowing whether they came from Key Vault
    or a local .env file.
    """
    secrets = load_keyvault_secrets(vault_url)
    for env_var, value in secrets.items():
        os.environ[env_var] = value
        log.debug("Injected %s from Key Vault into environment.", env_var)

    if secrets:
        log.info("Key Vault: %d secrets loaded into environment.", len(secrets))
    else:
        log.info("Key Vault: no secrets loaded (using .env / environment variables).")
