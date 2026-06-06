"""
etl-pipelines/python-local/loaders.py

Bulk-loads transformed DataFrames into Azure SQL dimension and fact tables
using the Temp-Table → MERGE pattern for idempotent, high-performance loads.

Pattern per dimension (SCD Type 1 — overwrite on change)
──────────────────────────────────────────────────────────
  1. CREATE TABLE #stg_<Entity>  (mirrors target column layout)
  2. cursor.fast_executemany = True  → bulk INSERT rows from DataFrame
  3. MERGE dbo.Dim<Entity> AS tgt USING #stg_<Entity> AS src ON natural key
     WHEN MATCHED THEN UPDATE ...
     WHEN NOT MATCHED THEN INSERT ...
  4. DROP TABLE #stg_<Entity>

Pattern per fact table (append-only with duplicate guard)
──────────────────────────────────────────────────────────
  1. CREATE TABLE #stg_<Fact>
  2. Bulk INSERT from DataFrame
  3. INSERT INTO dbo.Fact<X>  SELECT src.* FROM #stg WHERE NOT EXISTS (
         SELECT 1 FROM dbo.Fact<X> tgt WHERE tgt.NaturalKey = src.NaturalKey
     )
  4. DROP TABLE #stg_<Fact>

Security note
─────────────
  Table and column names in DDL/DML strings are hardcoded constants —
  never constructed from user input — so string formatting in SQL DDL
  carries zero injection risk.  All DATA values go through parameterised
  `?` placeholders via cursor.executemany (OWASP A03 compliant).
"""

import logging
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pyodbc

from config import ETL_CHUNK_SIZE

log = logging.getLogger(__name__)


# ── Generic staging helpers ───────────────────────────────────────────────────

def _df_to_rows(df: pd.DataFrame) -> List[tuple]:
    import numpy as np
    def _convert(val):
        if val is None:
            return None
        try:
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(val, np.integer):
            return int(val)
        if isinstance(val, np.floating):
            return float(val)
        if isinstance(val, np.bool_):
            return bool(val)
        return val
    return [
        tuple(_convert(val) for val in row)
        for row in df.itertuples(index=False, name=None)
    ]


def _bulk_stage(
    cursor: pyodbc.Cursor,
    staging_table: str,
    columns: List[str],
    rows: List[tuple],
    chunk_size: int = ETL_CHUNK_SIZE,
) -> int:
    """
    Insert `rows` into `staging_table` using multi-row VALUES inserts.
    Returns total row count staged.

    Each cursor.execute() inserts up to `rows_per_stmt` rows via a single
    INSERT … VALUES (r1), (r2), …, (rN) statement.  This avoids per-row
    round-trip latency and sidesteps the fast_executemany NULL-type-inference
    bug (pyodbc error 8114) entirely.  SQL Server's prepared-statement
    metadata resolves column types correctly regardless of NULL placement.

    SQL Server limits parameterised queries to 2 100 parameters total, so
    rows_per_stmt = max(1, 2000 // len(columns)) keeps us well under that cap.
    """
    if not rows:
        return 0

    n_cols = len(columns)
    col_list = ", ".join(f"[{c}]" for c in columns)
    rows_per_stmt = max(1, 2000 // n_cols)  # stay under SQL Server 2100-param limit

    total = 0
    for start in range(0, len(rows), rows_per_stmt):
        batch = rows[start: start + rows_per_stmt]
        row_placeholders = "(" + ", ".join(["?"] * n_cols) + ")"
        values_clause = ", ".join([row_placeholders] * len(batch))
        sql = f"INSERT INTO {staging_table} ({col_list}) VALUES {values_clause}"
        flat_params = [v for row in batch for v in row]
        cursor.execute(sql, flat_params)
        total += len(batch)
    return total


def _drop_staging(cursor: pyodbc.Cursor, staging_table: str) -> None:
    """Drop a temp staging table if it exists."""
    cursor.execute(f"IF OBJECT_ID('tempdb..{staging_table}') IS NOT NULL DROP TABLE {staging_table}")


# ── Dimension loaders ─────────────────────────────────────────────────────────

def load_dim_geography(conn: pyodbc.Connection, df: pd.DataFrame) -> Dict[Tuple, int]:
    """
    MERGE DimGeography and return a dict mapping
    (City, StateCode, Country, PostalCode) → GeographyKey.
    """
    if df.empty:
        return {}

    cursor = conn.cursor()
    try:
        _drop_staging(cursor, "#stg_geo")
        cursor.execute("""
            CREATE TABLE #stg_geo (
                City        NVARCHAR(100)  NOT NULL,
                StateCode   CHAR(2)        NOT NULL,
                Country     CHAR(2)        NOT NULL,
                CountryName NVARCHAR(60)   NOT NULL,
                State       NVARCHAR(50)   NOT NULL,
                WorldRegion VARCHAR(30)    NOT NULL,
                IsUSA       BIT            NOT NULL,
                PostalCode  VARCHAR(20)    NULL
            )
        """)
        cols = ["City", "StateCode", "Country", "CountryName", "State", "WorldRegion", "IsUSA", "PostalCode"]
        staged = _bulk_stage(cursor, "#stg_geo", cols, _df_to_rows(df[cols]))

        cursor.execute("""
            MERGE dbo.DimGeography AS tgt
            USING (
                SELECT DISTINCT City, StateCode, Country, CountryName, State,
                                WorldRegion, IsUSA, PostalCode
                FROM #stg_geo
            ) AS src
            ON  tgt.City       = src.City
            AND tgt.StateCode  = src.StateCode
            AND tgt.Country    = src.Country
            AND (tgt.PostalCode = src.PostalCode OR (tgt.PostalCode IS NULL AND src.PostalCode IS NULL))
            WHEN MATCHED THEN UPDATE SET
                tgt.CountryName = src.CountryName,
                tgt.WorldRegion = src.WorldRegion,
                tgt.IsUSA       = src.IsUSA
            WHEN NOT MATCHED BY TARGET THEN INSERT
                (City, StateCode, [State], Country, CountryName, WorldRegion, IsUSA, PostalCode)
            VALUES
                (src.City, src.StateCode, src.State, src.Country,
                 src.CountryName, src.WorldRegion, src.IsUSA, src.PostalCode);
        """)
        conn.commit()
        log.info("  DimGeography: %d rows staged, MERGE complete", staged)

        # Build lookup dict
        cursor.execute(
            "SELECT City, StateCode, Country, PostalCode, GeographyKey FROM dbo.DimGeography"
        )
        geo_map = {
            (
                (r[0] or "").strip(),
                (r[1] or "").strip(),
                (r[2] or "").strip(),
                r[3].strip() if r[3] is not None else None,
            ): r[4]
            for r in cursor.fetchall()
        }
        return geo_map

    except pyodbc.Error as exc:
        conn.rollback()
        raise RuntimeError(f"DimGeography load failed: {exc}") from exc
    finally:
        _drop_staging(cursor, "#stg_geo")
        cursor.close()


def load_dim_customer(conn: pyodbc.Connection, df: pd.DataFrame) -> Dict[str, int]:
    """
    MERGE DimCustomer (SCD Type 1). Returns CustomerID → CustomerKey dict.
    """
    if df.empty:
        return {}

    cursor = conn.cursor()
    try:
        _drop_staging(cursor, "#stg_cust")
        cursor.execute("""
            CREATE TABLE #stg_cust (
                CustomerID        UNIQUEIDENTIFIER NOT NULL,
                FirstName         NVARCHAR(50)     NOT NULL,
                LastName          NVARCHAR(50)     NOT NULL,
                FullName          NVARCHAR(101)    NOT NULL,
                Email             NVARCHAR(254)    NOT NULL,
                Phone             NVARCHAR(30)     NULL,
                DateOfBirth       DATE             NULL,
                AgeGroup          VARCHAR(5)       NULL,
                RegistrationDate  DATE             NOT NULL,
                CustomerSegment   VARCHAR(10)      NOT NULL,
                AccountStatus     VARCHAR(15)      NOT NULL,
                MarketingOptIn    BIT              NOT NULL,
                PreferredChannel  VARCHAR(20)      NULL,
                ReferralSource    VARCHAR(30)      NULL,
                LifetimeValue     DECIMAL(12,2)    NOT NULL
            )
        """)
        cols = list(df.columns)
        staged = _bulk_stage(cursor, "#stg_cust", cols, _df_to_rows(df))

        cursor.execute("""
            MERGE dbo.DimCustomer AS tgt
            USING #stg_cust AS src ON tgt.CustomerID = src.CustomerID
            WHEN MATCHED THEN UPDATE SET
                tgt.FirstName        = src.FirstName,
                tgt.LastName         = src.LastName,
                tgt.FullName         = src.FullName,
                tgt.Phone            = src.Phone,
                tgt.AgeGroup         = src.AgeGroup,
                tgt.CustomerSegment  = src.CustomerSegment,
                tgt.AccountStatus    = src.AccountStatus,
                tgt.MarketingOptIn   = src.MarketingOptIn,
                tgt.PreferredChannel = src.PreferredChannel,
                tgt.LifetimeValue    = src.LifetimeValue,
                tgt.RowUpdatedDate   = SYSUTCDATETIME()
            WHEN NOT MATCHED BY TARGET THEN INSERT (
                CustomerID, FirstName, LastName, FullName, Email, Phone,
                DateOfBirth, AgeGroup, RegistrationDate, CustomerSegment,
                AccountStatus, MarketingOptIn, PreferredChannel, ReferralSource, LifetimeValue
            ) VALUES (
                src.CustomerID, src.FirstName, src.LastName, src.FullName, src.Email, src.Phone,
                src.DateOfBirth, src.AgeGroup, src.RegistrationDate, src.CustomerSegment,
                src.AccountStatus, src.MarketingOptIn, src.PreferredChannel, src.ReferralSource,
                src.LifetimeValue
            );
        """)
        conn.commit()
        log.info("  DimCustomer: %d rows staged, MERGE complete", staged)

        cursor.execute("SELECT CustomerID, CustomerKey FROM dbo.DimCustomer")
        key_map = {str(r[0]).lower(): r[1] for r in cursor.fetchall()}
        return key_map

    except pyodbc.Error as exc:
        conn.rollback()
        raise RuntimeError(f"DimCustomer load failed: {exc}") from exc
    finally:
        _drop_staging(cursor, "#stg_cust")
        cursor.close()


def load_dim_product(conn: pyodbc.Connection, df: pd.DataFrame) -> Tuple[Dict[str, int], Dict[str, float]]:
    """
    MERGE DimProduct. Returns (ProductID → ProductKey, ProductID → CostPrice) dicts.
    The CostPrice dict is used by transform_fact_sales to compute CostOfGoods.
    """
    if df.empty:
        return {}, {}

    cursor = conn.cursor()
    try:
        _drop_staging(cursor, "#stg_prod")
        cursor.execute("""
            CREATE TABLE #stg_prod (
                ProductID      UNIQUEIDENTIFIER NOT NULL,
                ProductName    NVARCHAR(200)    NOT NULL,
                SKU            VARCHAR(20)      NOT NULL,
                Brand          NVARCHAR(100)    NOT NULL,
                Category       NVARCHAR(50)     NOT NULL,
                Subcategory    NVARCHAR(50)     NOT NULL,
                UnitPrice      DECIMAL(10,2)    NOT NULL,
                CostPrice      DECIMAL(10,2)    NOT NULL,
                MarginPct      DECIMAL(5,2)     NOT NULL,
                WeightKg       DECIMAL(8,2)     NULL,
                Supplier       NVARCHAR(150)    NULL,
                StockQuantity  INT              NOT NULL,
                ReorderLevel   INT              NOT NULL,
                LaunchDate     DATE             NULL,
                ProductStatus  VARCHAR(15)      NOT NULL,
                Rating         DECIMAL(3,1)     NULL,
                ReviewCount    INT              NOT NULL
            )
        """)
        cols = list(df.columns)
        staged = _bulk_stage(cursor, "#stg_prod", cols, _df_to_rows(df))

        cursor.execute("""
            MERGE dbo.DimProduct AS tgt
            USING #stg_prod AS src ON tgt.ProductID = src.ProductID
            WHEN MATCHED THEN UPDATE SET
                tgt.ProductName   = src.ProductName,
                tgt.UnitPrice     = src.UnitPrice,
                tgt.CostPrice     = src.CostPrice,
                tgt.MarginPct     = src.MarginPct,
                tgt.StockQuantity = src.StockQuantity,
                tgt.ProductStatus = src.ProductStatus,
                tgt.Rating        = src.Rating,
                tgt.ReviewCount   = src.ReviewCount,
                tgt.RowUpdatedDate= SYSUTCDATETIME()
            WHEN NOT MATCHED BY TARGET THEN INSERT (
                ProductID, ProductName, SKU, Brand, Category, Subcategory,
                UnitPrice, CostPrice, MarginPct, WeightKg, Supplier,
                StockQuantity, ReorderLevel, LaunchDate, ProductStatus,
                Rating, ReviewCount
            ) VALUES (
                src.ProductID, src.ProductName, src.SKU, src.Brand, src.Category,
                src.Subcategory, src.UnitPrice, src.CostPrice, src.MarginPct,
                src.WeightKg, src.Supplier, src.StockQuantity, src.ReorderLevel,
                src.LaunchDate, src.ProductStatus, src.Rating, src.ReviewCount
            );
        """)
        conn.commit()
        log.info("  DimProduct: %d rows staged, MERGE complete", staged)

        cursor.execute("SELECT ProductID, ProductKey, CostPrice FROM dbo.DimProduct")
        rows = cursor.fetchall()
        key_map  = {str(r[0]).lower(): r[1] for r in rows}
        cost_map = {str(r[0]).lower(): float(r[2]) for r in rows}
        return key_map, cost_map

    except pyodbc.Error as exc:
        conn.rollback()
        raise RuntimeError(f"DimProduct load failed: {exc}") from exc
    finally:
        _drop_staging(cursor, "#stg_prod")
        cursor.close()


def load_dim_employee(conn: pyodbc.Connection, df: pd.DataFrame) -> Dict[str, int]:
    """MERGE DimEmployee. Returns EmployeeID → EmployeeKey dict."""
    if df.empty:
        return {}

    cursor = conn.cursor()
    try:
        _drop_staging(cursor, "#stg_emp")
        cursor.execute("""
            CREATE TABLE #stg_emp (
                EmployeeID        UNIQUEIDENTIFIER NOT NULL,
                FirstName         NVARCHAR(50)     NOT NULL,
                LastName          NVARCHAR(50)     NOT NULL,
                FullName          NVARCHAR(101)    NOT NULL,
                Email             NVARCHAR(254)    NOT NULL,
                Department        NVARCHAR(50)     NOT NULL,
                Title             NVARCHAR(100)    NOT NULL,
                HireDate          DATE             NOT NULL,
                Salary            INT              NOT NULL,
                ManagerEmployeeID UNIQUEIDENTIFIER NULL,
                OfficeLocation    NVARCHAR(50)     NULL,
                EmployeeStatus    VARCHAR(15)      NOT NULL,
                PerformanceRating TINYINT          NOT NULL,
                YearsAtCompany    DECIMAL(5,1)     NOT NULL
            )
        """)
        cols = list(df.columns)
        staged = _bulk_stage(cursor, "#stg_emp", cols, _df_to_rows(df))

        cursor.execute("""
            MERGE dbo.DimEmployee AS tgt
            USING #stg_emp AS src ON tgt.EmployeeID = src.EmployeeID
            WHEN MATCHED THEN UPDATE SET
                tgt.Department        = src.Department,
                tgt.Title             = src.Title,
                tgt.Salary            = src.Salary,
                tgt.OfficeLocation    = src.OfficeLocation,
                tgt.EmployeeStatus    = src.EmployeeStatus,
                tgt.PerformanceRating = src.PerformanceRating,
                tgt.YearsAtCompany    = src.YearsAtCompany,
                tgt.RowUpdatedDate    = SYSUTCDATETIME()
            WHEN NOT MATCHED BY TARGET THEN INSERT (
                EmployeeID, FirstName, LastName, FullName, Email,
                Department, Title, HireDate, Salary, ManagerEmployeeID,
                OfficeLocation, EmployeeStatus, PerformanceRating, YearsAtCompany
            ) VALUES (
                src.EmployeeID, src.FirstName, src.LastName, src.FullName,
                src.Email, src.Department, src.Title, src.HireDate,
                src.Salary, src.ManagerEmployeeID, src.OfficeLocation,
                src.EmployeeStatus, src.PerformanceRating, src.YearsAtCompany
            );
        """)
        conn.commit()
        log.info("  DimEmployee: %d rows staged, MERGE complete", staged)

        cursor.execute("SELECT EmployeeID, EmployeeKey FROM dbo.DimEmployee")
        return {str(r[0]).lower(): r[1] for r in cursor.fetchall()}

    except pyodbc.Error as exc:
        conn.rollback()
        raise RuntimeError(f"DimEmployee load failed: {exc}") from exc
    finally:
        _drop_staging(cursor, "#stg_emp")
        cursor.close()


def load_dim_campaign(conn: pyodbc.Connection, df: pd.DataFrame) -> Dict[str, int]:
    """MERGE DimCampaign. Returns CampaignID → CampaignKey dict."""
    if df.empty:
        return {}

    cursor = conn.cursor()
    try:
        _drop_staging(cursor, "#stg_camp")
        cursor.execute("""
            CREATE TABLE #stg_camp (
                CampaignID     UNIQUEIDENTIFIER NOT NULL,
                CampaignName   NVARCHAR(200)    NOT NULL,
                CampaignType   VARCHAR(30)      NOT NULL,
                TargetSegment  VARCHAR(30)      NOT NULL,
                Region         VARCHAR(30)      NOT NULL,
                DurationDays   INT              NOT NULL,
                CampaignStatus VARCHAR(15)      NOT NULL
            )
        """)
        cols = list(df.columns)
        staged = _bulk_stage(cursor, "#stg_camp", cols, _df_to_rows(df))

        cursor.execute("""
            MERGE dbo.DimCampaign AS tgt
            USING #stg_camp AS src ON tgt.CampaignID = src.CampaignID
            WHEN MATCHED THEN UPDATE SET
                tgt.CampaignName   = src.CampaignName,
                tgt.CampaignStatus = src.CampaignStatus,
                tgt.DurationDays   = src.DurationDays
            WHEN NOT MATCHED BY TARGET THEN INSERT (
                CampaignID, CampaignName, CampaignType,
                TargetSegment, Region, DurationDays, CampaignStatus
            ) VALUES (
                src.CampaignID, src.CampaignName, src.CampaignType,
                src.TargetSegment, src.Region, src.DurationDays, src.CampaignStatus
            );
        """)
        conn.commit()
        log.info("  DimCampaign: %d rows staged, MERGE complete", staged)

        cursor.execute("SELECT CampaignID, CampaignKey FROM dbo.DimCampaign")
        return {str(r[0]).lower(): r[1] for r in cursor.fetchall()}

    except pyodbc.Error as exc:
        conn.rollback()
        raise RuntimeError(f"DimCampaign load failed: {exc}") from exc
    finally:
        _drop_staging(cursor, "#stg_camp")
        cursor.close()


# ── Fact loaders ──────────────────────────────────────────────────────────────

def load_fact_sales(conn: pyodbc.Connection, df: pd.DataFrame) -> int:
    """
    Append new FactSales rows (guard on LineItemID to prevent duplicates).
    Processes in chunks of ETL_CHUNK_SIZE.  Returns total rows inserted.
    """
    if df.empty:
        return 0

    cursor = conn.cursor()
    total_inserted = 0
    try:
        for start in range(0, len(df), ETL_CHUNK_SIZE):
            chunk = df.iloc[start: start + ETL_CHUNK_SIZE]

            _drop_staging(cursor, "#stg_fs")
            cursor.execute("""
                CREATE TABLE #stg_fs (
                    OrderDateKey     INT              NOT NULL,
                    CustomerKey      INT              NOT NULL,
                    ProductKey       INT              NOT NULL,
                    GeographyKey     INT              NOT NULL,
                    ShippedDateKey   INT              NULL,
                    DeliveredDateKey INT              NULL,
                    OrderID          UNIQUEIDENTIFIER NOT NULL,
                    LineItemID       UNIQUEIDENTIFIER NOT NULL,
                    OrderStatus      VARCHAR(15)      NOT NULL,
                    PaymentMethod    VARCHAR(20)      NOT NULL,
                    OrderChannel     VARCHAR(15)      NOT NULL,
                    Quantity         INT              NOT NULL,
                    DiscountAmount   DECIMAL(10,2)    NOT NULL,
                    LineTotal        DECIMAL(12,2)    NOT NULL,
                    ShippingAmount   DECIMAL(10,2)    NOT NULL,
                    TaxAmount        DECIMAL(10,2)    NOT NULL,
                    GrossRevenue     DECIMAL(12,2)    NOT NULL,
                    CostOfGoods      DECIMAL(12,2)    NOT NULL,
                    GrossProfit      DECIMAL(12,2)    NOT NULL,
                    UnitPrice        DECIMAL(10,2)    NOT NULL,
                    DiscountPct      TINYINT          NOT NULL
                )
            """)
            cols = list(chunk.columns)
            _bulk_stage(cursor, "#stg_fs", cols, _df_to_rows(chunk))

            cursor.execute("""
                INSERT INTO dbo.FactSales (
                    OrderDateKey, CustomerKey, ProductKey, GeographyKey,
                    ShippedDateKey, DeliveredDateKey,
                    OrderID, LineItemID, OrderStatus, PaymentMethod, OrderChannel,
                    Quantity, DiscountAmount, LineTotal, ShippingAmount, TaxAmount,
                    GrossRevenue, CostOfGoods, GrossProfit, UnitPrice, DiscountPct
                )
                SELECT
                    s.OrderDateKey, s.CustomerKey, s.ProductKey, s.GeographyKey,
                    s.ShippedDateKey, s.DeliveredDateKey,
                    s.OrderID, s.LineItemID, s.OrderStatus, s.PaymentMethod, s.OrderChannel,
                    s.Quantity, s.DiscountAmount, s.LineTotal, s.ShippingAmount, s.TaxAmount,
                    s.GrossRevenue, s.CostOfGoods, s.GrossProfit, s.UnitPrice, s.DiscountPct
                FROM #stg_fs s
                WHERE NOT EXISTS (
                    SELECT 1 FROM dbo.FactSales tgt WHERE tgt.LineItemID = s.LineItemID
                )
            """)
            inserted = cursor.rowcount
            conn.commit()
            total_inserted += inserted
            log.debug("  FactSales chunk %d–%d: %d inserted", start, start + len(chunk), inserted)
            _drop_staging(cursor, "#stg_fs")

    except pyodbc.Error as exc:
        conn.rollback()
        raise RuntimeError(f"FactSales load failed: {exc}") from exc
    finally:
        _drop_staging(cursor, "#stg_fs")
        cursor.close()

    log.info("  FactSales: %d new rows inserted", total_inserted)
    return total_inserted


def load_fact_tickets(conn: pyodbc.Connection, df: pd.DataFrame) -> int:
    """Append new FactSupportTickets rows (guard on TicketID). Returns inserted count."""
    if df.empty:
        return 0

    cursor = conn.cursor()
    total_inserted = 0
    try:
        for start in range(0, len(df), ETL_CHUNK_SIZE):
            chunk = df.iloc[start: start + ETL_CHUNK_SIZE]

            _drop_staging(cursor, "#stg_fst")
            cursor.execute("""
                CREATE TABLE #stg_fst (
                    CreatedDateKey      INT              NOT NULL,
                    ResolvedDateKey     INT              NULL,
                    CustomerKey         INT              NOT NULL,
                    AssignedEmployeeKey INT              NULL,
                    TicketID            UNIQUEIDENTIFIER NOT NULL,
                    Category            VARCHAR(20)      NOT NULL,
                    Priority            VARCHAR(10)      NOT NULL,
                    TicketStatus        VARCHAR(20)      NOT NULL,
                    InboundChannel      VARCHAR(25)      NOT NULL,
                    ResolutionHours     DECIMAL(8,1)     NULL,
                    SatisfactionRating  TINYINT          NULL,
                    FirstResponseHours  DECIMAL(6,2)     NULL,
                    IsEscalated         BIT              NOT NULL,
                    IsResolved          BIT              NOT NULL
                )
            """)
            cols = list(chunk.columns)
            _bulk_stage(cursor, "#stg_fst", cols, _df_to_rows(chunk))

            cursor.execute("""
                INSERT INTO dbo.FactSupportTickets (
                    CreatedDateKey, ResolvedDateKey, CustomerKey, AssignedEmployeeKey,
                    TicketID, Category, Priority, TicketStatus, InboundChannel,
                    ResolutionHours, SatisfactionRating, FirstResponseHours,
                    IsEscalated, IsResolved
                )
                SELECT
                    s.CreatedDateKey, s.ResolvedDateKey, s.CustomerKey, s.AssignedEmployeeKey,
                    s.TicketID, s.Category, s.Priority, s.TicketStatus, s.InboundChannel,
                    s.ResolutionHours, s.SatisfactionRating, s.FirstResponseHours,
                    s.IsEscalated, s.IsResolved
                FROM #stg_fst s
                WHERE NOT EXISTS (
                    SELECT 1 FROM dbo.FactSupportTickets tgt WHERE tgt.TicketID = s.TicketID
                )
            """)
            inserted = cursor.rowcount
            conn.commit()
            total_inserted += inserted
            _drop_staging(cursor, "#stg_fst")

    except pyodbc.Error as exc:
        conn.rollback()
        raise RuntimeError(f"FactSupportTickets load failed: {exc}") from exc
    finally:
        _drop_staging(cursor, "#stg_fst")
        cursor.close()

    log.info("  FactSupportTickets: %d new rows inserted", total_inserted)
    return total_inserted


def load_fact_campaign_performance(conn: pyodbc.Connection, df: pd.DataFrame) -> int:
    """Append new FactCampaignPerformance rows (guard on CampaignID). Returns inserted count."""
    if df.empty:
        return 0

    cursor = conn.cursor()
    total_inserted = 0
    try:
        _drop_staging(cursor, "#stg_fcp")
        cursor.execute("""
            CREATE TABLE #stg_fcp (
                CampaignKey           INT              NOT NULL,
                StartDateKey          INT              NOT NULL,
                EndDateKey            INT              NOT NULL,
                CampaignID            UNIQUEIDENTIFIER NOT NULL,
                Budget                DECIMAL(14,2)    NOT NULL,
                Spend                 DECIMAL(14,2)    NOT NULL,
                Impressions           INT              NOT NULL,
                Clicks                INT              NOT NULL,
                Conversions           INT              NOT NULL,
                RevenueGenerated      DECIMAL(14,2)    NOT NULL,
                DurationDays          INT              NOT NULL,
                ROI_Pct               DECIMAL(8,2)     NOT NULL,
                CTR_Pct               DECIMAL(8,3)     NOT NULL,
                ConversionRate_Pct    DECIMAL(8,3)     NOT NULL,
                CostPerClick          DECIMAL(10,4)    NOT NULL,
                CostPerConversion     DECIMAL(10,2)    NOT NULL,
                BudgetUtilization_Pct DECIMAL(8,2)     NOT NULL
            )
        """)
        cols = list(df.columns)
        _bulk_stage(cursor, "#stg_fcp", cols, _df_to_rows(df))

        cursor.execute("""
            INSERT INTO dbo.FactCampaignPerformance (
                CampaignKey, StartDateKey, EndDateKey, CampaignID,
                Budget, Spend, Impressions, Clicks, Conversions,
                RevenueGenerated, DurationDays, ROI_Pct, CTR_Pct,
                ConversionRate_Pct, CostPerClick, CostPerConversion,
                BudgetUtilization_Pct
            )
            SELECT
                s.CampaignKey, s.StartDateKey, s.EndDateKey, s.CampaignID,
                s.Budget, s.Spend, s.Impressions, s.Clicks, s.Conversions,
                s.RevenueGenerated, s.DurationDays, s.ROI_Pct, s.CTR_Pct,
                s.ConversionRate_Pct, s.CostPerClick, s.CostPerConversion,
                s.BudgetUtilization_Pct
            FROM #stg_fcp s
            WHERE NOT EXISTS (
                SELECT 1 FROM dbo.FactCampaignPerformance tgt
                WHERE tgt.CampaignID = s.CampaignID
            )
        """)
        total_inserted = cursor.rowcount
        conn.commit()

    except pyodbc.Error as exc:
        conn.rollback()
        raise RuntimeError(f"FactCampaignPerformance load failed: {exc}") from exc
    finally:
        _drop_staging(cursor, "#stg_fcp")
        cursor.close()

    log.info("  FactCampaignPerformance: %d new rows inserted", total_inserted)
    return total_inserted
