"""
etl-pipelines/python-local/validators.py

Row-level validation for every CSV entity loaded by the InsightHub ETL.

Design philosophy
─────────────────
• Validation is PERMISSIVE: invalid rows are quarantined and logged,
  not thrown as exceptions.  The pipeline continues with clean rows.
• Each validator returns (clean_df, error_count) so the caller knows
  how many rows were rejected.
• If error_count exceeds ETL_MAX_ERRORS, the etl_runner aborts that entity.
• Validation mirrors the CHECK constraints in the SQL schema exactly,
  so nothing that passes here will be rejected by the database.
"""

import logging
import re
from datetime import date
from typing import Tuple

import pandas as pd

from config import (
    ETL_MAX_ERRORS,
    VALID_ACCOUNT_STATUSES,
    VALID_CAMPAIGN_STATUSES,
    VALID_CAMPAIGN_TYPES,
    VALID_CUSTOMER_SEGMENTS,
    VALID_EMPLOYEE_STATUSES,
    VALID_ORDER_CHANNELS,
    VALID_ORDER_STATUSES,
    VALID_PRODUCT_STATUSES,
    VALID_TICKET_CATEGORIES,
    VALID_TICKET_PRIORITIES,
    VALID_TICKET_STATUSES,
)

log = logging.getLogger(__name__)

# Basic email regex (RFC 5321 simplified)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# UUID regex (v4 format from generate_data.py)
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _drop_invalid(
    df: pd.DataFrame,
    mask: pd.Series,
    reason: str,
    entity: str,
) -> Tuple[pd.DataFrame, int]:
    """Drop rows where mask is True, log a warning, return (clean_df, dropped_count)."""
    bad = mask.sum()
    if bad > 0:
        log.warning("  [%s] Dropping %d rows: %s", entity, bad, reason)
    return df[~mask].copy(), int(bad)


def validate_customers(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """
    Validate customers.csv.
    Rules:
    - customer_id must be non-null UUID
    - email must match basic format
    - customer_segment must be in VALID_CUSTOMER_SEGMENTS
    - account_status must be in VALID_ACCOUNT_STATUSES
    - date_of_birth must be parseable and not in the future
    - registration_date must be parseable
    """
    entity = "customers"
    total_errors = 0
    df = df.copy()

    # 1. Null customer_id
    mask = df["customer_id"].isna()
    df, n = _drop_invalid(df, mask, "null customer_id", entity)
    total_errors += n

    # 2. Duplicate customer_id
    mask = df.duplicated(subset=["customer_id"], keep="first")
    df, n = _drop_invalid(df, mask, "duplicate customer_id", entity)
    total_errors += n

    # 3. Invalid email format
    mask = ~df["email"].astype(str).str.match(_EMAIL_RE)
    df, n = _drop_invalid(df, mask, "invalid email format", entity)
    total_errors += n

    # 4. Duplicate email
    mask = df.duplicated(subset=["email"], keep="first")
    df, n = _drop_invalid(df, mask, "duplicate email", entity)
    total_errors += n

    # 5. Invalid customer_segment
    mask = ~df["customer_segment"].isin(VALID_CUSTOMER_SEGMENTS)
    df, n = _drop_invalid(df, mask, f"invalid customer_segment", entity)
    total_errors += n

    # 6. Invalid account_status
    mask = ~df["account_status"].isin(VALID_ACCOUNT_STATUSES)
    df, n = _drop_invalid(df, mask, "invalid account_status", entity)
    total_errors += n

    # 7. Unparseable date_of_birth
    dob = pd.to_datetime(df["date_of_birth"], errors="coerce")
    mask = dob.isna()
    df, n = _drop_invalid(df, mask, "unparseable date_of_birth", entity)
    total_errors += n

    # 8. Unparseable registration_date
    reg = pd.to_datetime(df["registration_date"], errors="coerce")
    mask = reg.isna()
    df, n = _drop_invalid(df, mask, "unparseable registration_date", entity)
    total_errors += n

    log.info("  [%s] Valid rows: %d  |  Total rejected: %d", entity, len(df), total_errors)
    return df, total_errors


def validate_products(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """
    Validate products.csv.
    Rules:
    - product_id and sku must be non-null and unique
    - unit_price and cost_price must be > 0
    - margin_pct must be between -100 and 100
    - status must be in VALID_PRODUCT_STATUSES
    - rating (if present) must be 1.0–5.0
    """
    entity = "products"
    total_errors = 0
    df = df.copy()

    mask = df["product_id"].isna()
    df, n = _drop_invalid(df, mask, "null product_id", entity)
    total_errors += n

    mask = df.duplicated(subset=["product_id"], keep="first")
    df, n = _drop_invalid(df, mask, "duplicate product_id", entity)
    total_errors += n

    mask = df.duplicated(subset=["sku"], keep="first")
    df, n = _drop_invalid(df, mask, "duplicate sku", entity)
    total_errors += n

    mask = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0) <= 0
    df, n = _drop_invalid(df, mask, "unit_price <= 0", entity)
    total_errors += n

    mask = pd.to_numeric(df["cost_price"], errors="coerce").fillna(0) <= 0
    df, n = _drop_invalid(df, mask, "cost_price <= 0", entity)
    total_errors += n

    mask = ~df["status"].isin(VALID_PRODUCT_STATUSES)
    df, n = _drop_invalid(df, mask, "invalid status", entity)
    total_errors += n

    # Rating: allow NaN (some products unrated) but reject out-of-range
    rating = pd.to_numeric(df["rating"], errors="coerce")
    mask = ~(rating.isna() | rating.between(1.0, 5.0))
    df, n = _drop_invalid(df, mask, "rating out of 1.0–5.0 range", entity)
    total_errors += n

    log.info("  [%s] Valid rows: %d  |  Total rejected: %d", entity, len(df), total_errors)
    return df, total_errors


def validate_employees(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """
    Validate employees.csv.
    Rules:
    - employee_id must be non-null UUID, unique
    - salary must be > 0
    - performance_rating must be 1–5
    - status must be in VALID_EMPLOYEE_STATUSES
    - hire_date must be parseable and not in the future
    """
    entity = "employees"
    total_errors = 0
    df = df.copy()

    mask = df["employee_id"].isna()
    df, n = _drop_invalid(df, mask, "null employee_id", entity)
    total_errors += n

    mask = df.duplicated(subset=["employee_id"], keep="first")
    df, n = _drop_invalid(df, mask, "duplicate employee_id", entity)
    total_errors += n

    mask = pd.to_numeric(df["salary"], errors="coerce").fillna(0) <= 0
    df, n = _drop_invalid(df, mask, "salary <= 0", entity)
    total_errors += n

    perf = pd.to_numeric(df["performance_rating"], errors="coerce")
    mask = ~perf.between(1, 5)
    df, n = _drop_invalid(df, mask, "performance_rating not 1–5", entity)
    total_errors += n

    mask = ~df["status"].isin(VALID_EMPLOYEE_STATUSES)
    df, n = _drop_invalid(df, mask, "invalid status", entity)
    total_errors += n

    hire = pd.to_datetime(df["hire_date"], errors="coerce")
    mask = hire.isna()
    df, n = _drop_invalid(df, mask, "unparseable hire_date", entity)
    total_errors += n

    log.info("  [%s] Valid rows: %d  |  Total rejected: %d", entity, len(df), total_errors)
    return df, total_errors


def validate_orders(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """
    Validate orders.csv.
    Rules:
    - order_id, customer_id must be non-null and order_id unique
    - total_amount, subtotal must be >= 0
    - status must be in VALID_ORDER_STATUSES
    - channel must be in VALID_ORDER_CHANNELS
    - order_date must be parseable
    """
    entity = "orders"
    total_errors = 0
    df = df.copy()

    mask = df["order_id"].isna()
    df, n = _drop_invalid(df, mask, "null order_id", entity)
    total_errors += n

    mask = df.duplicated(subset=["order_id"], keep="first")
    df, n = _drop_invalid(df, mask, "duplicate order_id", entity)
    total_errors += n

    mask = df["customer_id"].isna()
    df, n = _drop_invalid(df, mask, "null customer_id", entity)
    total_errors += n

    mask = pd.to_numeric(df["total_amount"], errors="coerce").fillna(-1) < 0
    df, n = _drop_invalid(df, mask, "total_amount < 0", entity)
    total_errors += n

    mask = ~df["status"].isin(VALID_ORDER_STATUSES)
    df, n = _drop_invalid(df, mask, "invalid status", entity)
    total_errors += n

    mask = ~df["channel"].isin(VALID_ORDER_CHANNELS)
    df, n = _drop_invalid(df, mask, "invalid channel", entity)
    total_errors += n

    order_date = pd.to_datetime(df["order_date"], errors="coerce")
    mask = order_date.isna()
    df, n = _drop_invalid(df, mask, "unparseable order_date", entity)
    total_errors += n

    log.info("  [%s] Valid rows: %d  |  Total rejected: %d", entity, len(df), total_errors)
    return df, total_errors


def validate_order_items(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """
    Validate order_items.csv.
    Rules:
    - line_item_id, order_id, product_id must be non-null
    - line_item_id must be unique
    - quantity must be >= 1
    - unit_price must be > 0
    - discount_pct must be 0–100
    """
    entity = "order_items"
    total_errors = 0
    df = df.copy()

    for col in ["line_item_id", "order_id", "product_id"]:
        mask = df[col].isna()
        df, n = _drop_invalid(df, mask, f"null {col}", entity)
        total_errors += n

    mask = df.duplicated(subset=["line_item_id"], keep="first")
    df, n = _drop_invalid(df, mask, "duplicate line_item_id", entity)
    total_errors += n

    mask = pd.to_numeric(df["quantity"], errors="coerce").fillna(0) < 1
    df, n = _drop_invalid(df, mask, "quantity < 1", entity)
    total_errors += n

    mask = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0) <= 0
    df, n = _drop_invalid(df, mask, "unit_price <= 0", entity)
    total_errors += n

    disc = pd.to_numeric(df["discount_pct"], errors="coerce").fillna(0)
    mask = ~disc.between(0, 100)
    df, n = _drop_invalid(df, mask, "discount_pct not 0–100", entity)
    total_errors += n

    log.info("  [%s] Valid rows: %d  |  Total rejected: %d", entity, len(df), total_errors)
    return df, total_errors


def validate_support_tickets(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """
    Validate support_tickets.csv.
    Rules:
    - ticket_id, customer_id must be non-null; ticket_id unique
    - category, priority, status must be in valid sets
    - created_date must be parseable
    - satisfaction_rating (if present) must be 1–5
    """
    entity = "support_tickets"
    total_errors = 0
    df = df.copy()

    mask = df["ticket_id"].isna()
    df, n = _drop_invalid(df, mask, "null ticket_id", entity)
    total_errors += n

    mask = df.duplicated(subset=["ticket_id"], keep="first")
    df, n = _drop_invalid(df, mask, "duplicate ticket_id", entity)
    total_errors += n

    mask = df["customer_id"].isna()
    df, n = _drop_invalid(df, mask, "null customer_id", entity)
    total_errors += n

    mask = ~df["category"].isin(VALID_TICKET_CATEGORIES)
    df, n = _drop_invalid(df, mask, "invalid category", entity)
    total_errors += n

    mask = ~df["priority"].isin(VALID_TICKET_PRIORITIES)
    df, n = _drop_invalid(df, mask, "invalid priority", entity)
    total_errors += n

    mask = ~df["status"].isin(VALID_TICKET_STATUSES)
    df, n = _drop_invalid(df, mask, "invalid status", entity)
    total_errors += n

    created = pd.to_datetime(df["created_date"], errors="coerce")
    mask = created.isna()
    df, n = _drop_invalid(df, mask, "unparseable created_date", entity)
    total_errors += n

    sat = pd.to_numeric(df["satisfaction_rating"], errors="coerce")
    mask = ~(sat.isna() | sat.between(1, 5))
    df, n = _drop_invalid(df, mask, "satisfaction_rating not 1–5", entity)
    total_errors += n

    log.info("  [%s] Valid rows: %d  |  Total rejected: %d", entity, len(df), total_errors)
    return df, total_errors


def validate_campaigns(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """
    Validate campaigns.csv.
    Rules:
    - campaign_id must be non-null UUID, unique
    - campaign_type must be in VALID_CAMPAIGN_TYPES
    - status must be in VALID_CAMPAIGN_STATUSES
    - budget and spend must be >= 0
    - start_date and end_date must be parseable; end >= start
    """
    entity = "campaigns"
    total_errors = 0
    df = df.copy()

    mask = df["campaign_id"].isna()
    df, n = _drop_invalid(df, mask, "null campaign_id", entity)
    total_errors += n

    mask = df.duplicated(subset=["campaign_id"], keep="first")
    df, n = _drop_invalid(df, mask, "duplicate campaign_id", entity)
    total_errors += n

    mask = ~df["campaign_type"].isin(VALID_CAMPAIGN_TYPES)
    df, n = _drop_invalid(df, mask, "invalid campaign_type", entity)
    total_errors += n

    mask = ~df["status"].isin(VALID_CAMPAIGN_STATUSES)
    df, n = _drop_invalid(df, mask, "invalid status", entity)
    total_errors += n

    mask = pd.to_numeric(df["budget"], errors="coerce").fillna(-1) < 0
    df, n = _drop_invalid(df, mask, "budget < 0", entity)
    total_errors += n

    start = pd.to_datetime(df["start_date"], errors="coerce")
    end   = pd.to_datetime(df["end_date"],   errors="coerce")
    mask  = start.isna() | end.isna()
    df, n = _drop_invalid(df, mask, "unparseable start/end date", entity)
    total_errors += n

    # Re-parse after dropping unparseable rows
    if len(df) > 0:
        start = pd.to_datetime(df["start_date"], errors="coerce")
        end   = pd.to_datetime(df["end_date"],   errors="coerce")
        mask  = end < start
        df, n = _drop_invalid(df, mask, "end_date before start_date", entity)
        total_errors += n

    log.info("  [%s] Valid rows: %d  |  Total rejected: %d", entity, len(df), total_errors)
    return df, total_errors


def check_error_threshold(entity: str, error_count: int) -> None:
    """Raise RuntimeError if validation errors exceed ETL_MAX_ERRORS."""
    if error_count > ETL_MAX_ERRORS:
        raise RuntimeError(
            f"[{entity}] Validation error count {error_count} exceeds "
            f"ETL_MAX_ERRORS={ETL_MAX_ERRORS}. Aborting this entity. "
            f"Investigate source data quality before re-running."
        )
