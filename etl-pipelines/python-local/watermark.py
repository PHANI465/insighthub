"""
etl-pipelines/python-local/watermark.py

Implements the watermark (high-water mark) pattern for incremental loading.

How it works
────────────
A table called dbo.ETL_Watermark in Azure SQL stores one row per entity
(e.g. 'FactSales').  Each row holds the timestamp of the last successfully
loaded record.  On every run:
  1. Read the watermark  →  only process records newer than that timestamp
  2. After successful load  →  update the watermark to the new max timestamp

This ensures:
  • Full load on first run (watermark starts at '2000-01-01')
  • Incremental on subsequent runs — no duplicate inserts
  • Idempotent: re-running after a failure is safe (re-processes since last
    successful watermark)

Watermark table is created automatically on first use.
"""

import logging
from datetime import datetime
from typing import Optional

import pyodbc

log = logging.getLogger(__name__)

# SQL to create the watermark table (idempotent)
_CREATE_WATERMARK_TABLE = """
IF OBJECT_ID('dbo.ETL_Watermark', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ETL_Watermark
    (
        EntityName      VARCHAR(100)    NOT NULL,
        LastLoadedAt    DATETIME2(0)    NOT NULL    DEFAULT '2000-01-01 00:00:00',
        LastFileLoaded  VARCHAR(500)    NULL,
        RowsInserted    INT             NOT NULL    DEFAULT 0,
        RowsUpdated     INT             NOT NULL    DEFAULT 0,
        RowsSkipped     INT             NOT NULL    DEFAULT 0,
        LastRunStatus   VARCHAR(20)     NOT NULL    DEFAULT 'Never',
        LastRunDate     DATETIME2(0)    NULL,
        CONSTRAINT PK_ETL_Watermark PRIMARY KEY (EntityName)
    );
END
"""

_UPSERT_WATERMARK = """
MERGE dbo.ETL_Watermark AS tgt
USING (
    SELECT
        ? AS EntityName,
        ? AS LastLoadedAt,
        ? AS LastFileLoaded,
        ? AS RowsInserted,
        ? AS RowsUpdated,
        ? AS RowsSkipped,
        ? AS LastRunStatus,
        SYSUTCDATETIME() AS LastRunDate
) AS src ON tgt.EntityName = src.EntityName
WHEN MATCHED THEN UPDATE SET
    tgt.LastLoadedAt   = src.LastLoadedAt,
    tgt.LastFileLoaded = src.LastFileLoaded,
    tgt.RowsInserted   = tgt.RowsInserted + src.RowsInserted,
    tgt.RowsUpdated    = tgt.RowsUpdated  + src.RowsUpdated,
    tgt.RowsSkipped    = tgt.RowsSkipped  + src.RowsSkipped,
    tgt.LastRunStatus  = src.LastRunStatus,
    tgt.LastRunDate    = src.LastRunDate
WHEN NOT MATCHED THEN INSERT (
    EntityName, LastLoadedAt, LastFileLoaded,
    RowsInserted, RowsUpdated, RowsSkipped,
    LastRunStatus, LastRunDate
) VALUES (
    src.EntityName, src.LastLoadedAt, src.LastFileLoaded,
    src.RowsInserted, src.RowsUpdated, src.RowsSkipped,
    src.LastRunStatus, src.LastRunDate
);
"""

_GET_WATERMARK = """
SELECT LastLoadedAt
FROM dbo.ETL_Watermark
WHERE EntityName = ?
"""

_EPOCH = datetime(2000, 1, 1, 0, 0, 0)


def ensure_watermark_table(conn: pyodbc.Connection) -> None:
    """Create dbo.ETL_Watermark if it does not already exist."""
    cursor = conn.cursor()
    try:
        cursor.execute(_CREATE_WATERMARK_TABLE)
        conn.commit()
        log.debug("ETL_Watermark table verified/created.")
    finally:
        cursor.close()


def get_watermark(conn: pyodbc.Connection, entity_name: str) -> datetime:
    """
    Return the last successfully loaded timestamp for `entity_name`.
    Returns epoch (2000-01-01) if no record exists yet — triggers a full load.

    Parameters
    ----------
    conn         : Open pyodbc connection
    entity_name  : Table name, e.g. 'FactSales', 'FactSupportTickets'
    """
    cursor = conn.cursor()
    try:
        cursor.execute(_GET_WATERMARK, (entity_name,))
        row = cursor.fetchone()
        if row is None:
            log.info("  No watermark found for %s — will do full load.", entity_name)
            return _EPOCH
        wm = row[0]
        if wm is None:
            return _EPOCH
        log.info("  Watermark for %s: %s", entity_name, wm)
        return wm if isinstance(wm, datetime) else datetime.fromisoformat(str(wm))
    finally:
        cursor.close()


def update_watermark(
    conn: pyodbc.Connection,
    entity_name: str,
    last_loaded_at: datetime,
    file_loaded: Optional[str] = None,
    rows_inserted: int = 0,
    rows_updated: int = 0,
    rows_skipped: int = 0,
    status: str = "Success",
) -> None:
    """
    Upsert the watermark for `entity_name` after a successful load.
    Safe to call multiple times (MERGE is idempotent on EntityName).

    Parameters
    ----------
    last_loaded_at : The maximum record timestamp successfully loaded
    file_loaded    : Blob path of the file that was processed
    rows_inserted  : Count of new rows added to target table
    rows_updated   : Count of existing rows updated (dimensions only)
    rows_skipped   : Count of rows rejected by validation
    status         : 'Success', 'Partial', or 'Failed'
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            _UPSERT_WATERMARK,
            (
                entity_name,
                last_loaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                file_loaded,
                rows_inserted,
                rows_updated,
                rows_skipped,
                status,
            ),
        )
        conn.commit()
        log.info(
            "  Watermark updated — %s: inserted=%d updated=%d skipped=%d status=%s",
            entity_name,
            rows_inserted,
            rows_updated,
            rows_skipped,
            status,
        )
    except pyodbc.Error as exc:
        conn.rollback()
        log.error("Failed to update watermark for %s: %s", entity_name, exc)
        raise
    finally:
        cursor.close()
