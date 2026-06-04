"""
data-generation/upload_to_blob.py

Uploads every CSV produced by generate_data.py to an Azure Blob Storage
container so that Azure Data Factory and ETL pipelines can read them.

Authentication uses a storage-account connection string composed from
environment variables — no credentials are ever hardcoded.

Run this after generate_data.py:
  python data-generation/upload_to_blob.py
"""

import logging
import os
from pathlib import Path

from azure.core.exceptions import AzureError, ResourceExistsError
from azure.storage.blob import BlobServiceClient, ContentSettings
from dotenv import load_dotenv

# ── Load .env for local development ────────────────────────────────────────
load_dotenv()

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Environment validation ───────────────────────────────────────────────────
def _require_env(name: str) -> str:
    """
    Return the value of an environment variable or raise a clear error.
    This ensures a missing variable fails immediately with an actionable
    message instead of silently causing an auth failure downstream.
    """
    value = os.getenv(name)
    if not value:
        raise ValueError(
            f"Required environment variable '{name}' is not set. "
            f"Copy .env.example → .env and fill in the value."
        )
    return value


# Read and validate every required variable up front
STORAGE_ACCOUNT_NAME: str = _require_env("STORAGE_ACCOUNT_NAME")
STORAGE_ACCOUNT_KEY:  str = _require_env("STORAGE_ACCOUNT_KEY")
STORAGE_CONTAINER:    str = _require_env("STORAGE_CONTAINER")

# Optional — default keeps raw files under a dedicated prefix
BLOB_RAW_SUBFOLDER: str = os.getenv("BLOB_RAW_SUBFOLDER", "raw/insighthub")
OUTPUT_DIR: Path = Path(
    os.getenv("DATA_OUTPUT_DIR", str(Path(__file__).parent / "output"))
)


# ── Azure Blob helpers ───────────────────────────────────────────────────────
def build_connection_string() -> str:
    """
    Assemble an Azure Blob Storage connection string from individual
    environment variables.  Using individual vars (not a full connection
    string secret) gives finer-grained Key Vault access policies.
    """
    return (
        f"DefaultEndpointsProtocol=https;"
        f"AccountName={STORAGE_ACCOUNT_NAME};"
        f"AccountKey={STORAGE_ACCOUNT_KEY};"
        f"EndpointSuffix=core.windows.net"
    )


def get_blob_service_client() -> BlobServiceClient:
    """Create and return an authenticated BlobServiceClient."""
    conn_str = build_connection_string()
    try:
        client = BlobServiceClient.from_connection_string(conn_str)
        return client
    except ValueError as exc:
        raise ValueError(
            f"Could not build BlobServiceClient — check STORAGE_ACCOUNT_NAME "
            f"and STORAGE_ACCOUNT_KEY in your .env file. Detail: {exc}"
        ) from exc


def ensure_container(client: BlobServiceClient, container_name: str) -> None:
    """
    Create the blob container if it does not already exist.
    Silently continues if it already exists (ResourceExistsError is expected).
    """
    try:
        client.create_container(container_name)
        log.info("Created container: %s", container_name)
    except ResourceExistsError:
        log.debug("Container '%s' already exists — skipping creation.", container_name)
    except AzureError as exc:
        log.error("Could not create/verify container '%s': %s", container_name, exc)
        raise


def upload_csv(
    client: BlobServiceClient,
    local_path: Path,
    container: str,
    blob_name: str,
) -> None:
    """
    Upload a single CSV file to Azure Blob Storage.

    Uses overwrite=True so re-running the generator and uploader always
    refreshes the data in blob storage (idempotent operation).
    Content-Type is set to text/csv so Azure services recognise the format.
    """
    blob_client = client.get_blob_client(container=container, blob=blob_name)
    csv_settings = ContentSettings(content_type="text/csv; charset=utf-8")

    with open(local_path, "rb") as fh:
        blob_client.upload_blob(
            fh,
            overwrite=True,
            content_settings=csv_settings,
        )

    blob_url = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{container}/{blob_name}"
    log.info("  ✓ %-30s → %s", local_path.name, blob_url)


# ── Main upload workflow ─────────────────────────────────────────────────────
def upload_all_csvs() -> None:
    """
    Find every CSV file in OUTPUT_DIR and upload it to Azure Blob Storage
    under the BLOB_RAW_SUBFOLDER prefix.

    Raises
    ------
    FileNotFoundError
        If OUTPUT_DIR contains no CSV files (generate_data.py not yet run).
    AzureError
        If any upload fails — partial uploads are logged before re-raising.
    """
    if not OUTPUT_DIR.exists():
        raise FileNotFoundError(
            f"Output directory not found: {OUTPUT_DIR}\n"
            "Run python data-generation/generate_data.py first."
        )

    csv_files = sorted(OUTPUT_DIR.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(
            f"No CSV files found in {OUTPUT_DIR}.\n"
            "Run python data-generation/generate_data.py first."
        )

    log.info("=" * 60)
    log.info("InsightHub — Azure Blob Upload")
    log.info("  Account   : %s", STORAGE_ACCOUNT_NAME)
    log.info("  Container : %s", STORAGE_CONTAINER)
    log.info("  Prefix    : %s", BLOB_RAW_SUBFOLDER)
    log.info("  Files     : %d CSV files found", len(csv_files))
    log.info("=" * 60)

    client = get_blob_service_client()
    ensure_container(client, STORAGE_CONTAINER)

    failed: list = []
    for csv_path in csv_files:
        blob_name = f"{BLOB_RAW_SUBFOLDER}/{csv_path.name}"
        try:
            upload_csv(client, csv_path, STORAGE_CONTAINER, blob_name)
        except (AzureError, OSError) as exc:
            log.error("FAILED to upload %s: %s", csv_path.name, exc)
            failed.append(csv_path.name)

    log.info("=" * 60)
    if failed:
        log.error("⚠️  %d file(s) failed to upload: %s", len(failed), ", ".join(failed))
        raise RuntimeError(f"Upload incomplete — {len(failed)} file(s) failed.")
    else:
        log.info(
            "✅  All %d CSV files uploaded to container '%s' under prefix '%s'.",
            len(csv_files),
            STORAGE_CONTAINER,
            BLOB_RAW_SUBFOLDER,
        )
    log.info("=" * 60)


if __name__ == "__main__":
    upload_all_csvs()
