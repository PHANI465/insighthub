"""
etl-pipelines/python-local/blob_reader.py

Downloads CSV files from Azure Blob Storage and returns them as
pandas DataFrames.  Streams the file content in memory to avoid
writing temporary files to disk.

All connection details come from environment variables via config.py.
"""

import io
import logging
from typing import Dict, Iterator, Optional

import pandas as pd
from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from config import (
    BLOB_RAW_SUBFOLDER,
    CSV_FILES,
    ETL_CHUNK_SIZE,
    STORAGE_ACCOUNT_KEY,
    STORAGE_ACCOUNT_NAME,
    STORAGE_CONTAINER,
)

log = logging.getLogger(__name__)


def _build_blob_conn_string() -> str:
    """Build the Blob Storage connection string from env vars."""
    return (
        f"DefaultEndpointsProtocol=https;"
        f"AccountName={STORAGE_ACCOUNT_NAME};"
        f"AccountKey={STORAGE_ACCOUNT_KEY};"
        f"EndpointSuffix=core.windows.net"
    )


def _get_blob_client(blob_name: str):
    """Return a BlobClient for the given blob path."""
    svc = BlobServiceClient.from_connection_string(_build_blob_conn_string())
    return svc.get_blob_client(container=STORAGE_CONTAINER, blob=blob_name)


def download_csv(
    entity: str,
    dtype: Optional[Dict[str, str]] = None,
    parse_dates: Optional[list] = None,
) -> pd.DataFrame:
    """
    Download a complete CSV from Blob Storage and return as a single DataFrame.
    Used for small dimension tables (customers, products, employees, campaigns).

    Parameters
    ----------
    entity      : Key from config.CSV_FILES (e.g. 'customers')
    dtype       : Optional column dtype overrides passed to pd.read_csv
    parse_dates : Optional list of columns to parse as datetime

    Raises
    ------
    FileNotFoundError  : blob does not exist
    AzureError         : network or auth error
    """
    filename = CSV_FILES.get(entity)
    if not filename:
        raise ValueError(f"Unknown entity '{entity}'. Valid keys: {list(CSV_FILES)}")

    blob_path = f"{BLOB_RAW_SUBFOLDER}/{filename}"
    log.info("  Downloading %s from blob: %s", entity, blob_path)

    try:
        client = _get_blob_client(blob_path)
        raw = client.download_blob().readall()
    except ResourceNotFoundError:
        raise FileNotFoundError(
            f"Blob not found: {STORAGE_CONTAINER}/{blob_path}. "
            f"Run data-generation/upload_to_blob.py first."
        )
    except AzureError as exc:
        raise RuntimeError(f"Azure error downloading {blob_path}: {exc}") from exc

    buffer = io.BytesIO(raw)
    df = pd.read_csv(
        buffer,
        dtype=dtype,
        parse_dates=parse_dates if parse_dates else False,
        low_memory=False,
    )
    log.info("  ✓ Downloaded %d rows for %s", len(df), entity)
    return df


def stream_csv_chunks(
    entity: str,
    dtype: Optional[Dict[str, str]] = None,
    chunk_size: int = ETL_CHUNK_SIZE,
) -> Iterator[pd.DataFrame]:
    """
    Download a CSV and yield it as DataFrame chunks of `chunk_size` rows.
    Used for large fact source files (orders, order_items, support_tickets).

    Yields
    ------
    pd.DataFrame chunks, each with at most `chunk_size` rows.
    """
    filename = CSV_FILES.get(entity)
    if not filename:
        raise ValueError(f"Unknown entity '{entity}'. Valid keys: {list(CSV_FILES)}")

    blob_path = f"{BLOB_RAW_SUBFOLDER}/{filename}"
    log.info("  Streaming %s in chunks of %d rows", blob_path, chunk_size)

    try:
        client = _get_blob_client(blob_path)
        raw = client.download_blob().readall()
    except ResourceNotFoundError:
        raise FileNotFoundError(
            f"Blob not found: {STORAGE_CONTAINER}/{blob_path}. "
            f"Run upload_to_blob.py first."
        )
    except AzureError as exc:
        raise RuntimeError(f"Azure error streaming {blob_path}: {exc}") from exc

    buffer = io.BytesIO(raw)
    reader = pd.read_csv(buffer, dtype=dtype, chunksize=chunk_size, low_memory=False)
    chunk_num = 0
    for chunk in reader:
        chunk_num += 1
        log.debug("    Chunk %d: %d rows", chunk_num, len(chunk))
        yield chunk

    log.info("  ✓ Streamed %d chunks for %s", chunk_num, entity)


def list_raw_blobs() -> list[str]:
    """
    List all blob names under BLOB_RAW_SUBFOLDER.
    Used by etl_runner to verify source files exist before starting the pipeline.
    """
    svc = BlobServiceClient.from_connection_string(_build_blob_conn_string())
    container_client = svc.get_container_client(STORAGE_CONTAINER)
    blobs = [
        b.name
        for b in container_client.list_blobs(name_starts_with=BLOB_RAW_SUBFOLDER)
    ]
    return blobs
