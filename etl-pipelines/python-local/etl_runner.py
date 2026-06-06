"""
etl-pipelines/python-local/etl_runner.py

Main ETL orchestrator for InsightHub.
Coordinates the full pipeline: Blob → validate → transform → Azure SQL.

Execution order (respects FK dependencies)
───────────────────────────────────────────
  Dimensions first (no FK dependencies between them):
    1. DimGeography    (extracted from orders shipping addresses)
    2. DimCustomer
    3. DimProduct
    4. DimEmployee
    5. DimCampaign

  Facts second (require all dimensions loaded first):
    6. FactSales                (→ DimDate, DimCustomer, DimProduct, DimGeography)
    7. FactSupportTickets       (→ DimDate, DimCustomer, DimEmployee)
    8. FactCampaignPerformance  (→ DimDate, DimCampaign)

Watermark pattern
─────────────────
  • Dimensions: always full MERGE (small tables, idempotent)
  • Fact tables: incremental — only records with date > watermark are loaded
  • After each successful fact load, watermark is updated to max date in loaded data

Usage
─────
  # Full pipeline
  python etl-pipelines/python-local/etl_runner.py

  # Single entity
  python etl-pipelines/python-local/etl_runner.py --entity customers

  # Smoke test (connection + blob existence check only)
  python etl-pipelines/python-local/etl_runner.py --test

  # Force full reload of all fact tables (ignore watermarks)
  python etl-pipelines/python-local/etl_runner.py --full-reload
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from config import CSV_FILES, ETL_LOG_LEVEL
from db_connection import get_connection, test_connection
from blob_reader import download_csv, list_raw_blobs, stream_csv_chunks
from validators import (
    check_error_threshold,
    validate_campaigns,
    validate_customers,
    validate_employees,
    validate_order_items,
    validate_orders,
    validate_products,
    validate_support_tickets,
)
from transformers import (
    extract_geographies,
    transform_campaigns,
    transform_customers,
    transform_employees,
    transform_fact_campaigns,
    transform_fact_sales,
    transform_fact_tickets,
    transform_products,
)
from loaders import (
    load_dim_campaign,
    load_dim_customer,
    load_dim_employee,
    load_dim_geography,
    load_dim_product,
    load_fact_campaign_performance,
    load_fact_sales,
    load_fact_tickets,
)
from watermark import ensure_watermark_table, get_watermark, update_watermark

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, ETL_LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Suppress verbose HTTP-level logs from Azure SDK (they appear at INFO but are noise)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.storage.blob").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

_EPOCH = datetime(2000, 1, 1)


# ── Pipeline stages ───────────────────────────────────────────────────────────

def run_dimensions(conn, full_reload: bool = False) -> dict:
    """
    Load all five dimension tables.
    Returns a context dict with all FK lookup maps needed by fact loaders.
    """
    ctx = {}

    # ── 1. DimGeography (extracted from orders) ──────────────────────────────
    log.info("[ 1/5 ] DimGeography …")
    orders_raw = download_csv("orders")
    ctx["geography_key_map"] = load_dim_geography(conn, extract_geographies(orders_raw))
    ctx["orders_raw"] = orders_raw   # Reuse for FactSales — avoid double download

    # ── 2. DimCustomer ───────────────────────────────────────────────────────
    log.info("[ 2/5 ] DimCustomer …")
    raw = download_csv("customers")
    raw, errors = validate_customers(raw)
    check_error_threshold("customers", errors)
    ctx["customer_key_map"] = load_dim_customer(conn, transform_customers(raw))

    # ── 3. DimProduct ────────────────────────────────────────────────────────
    log.info("[ 3/5 ] DimProduct …")
    raw = download_csv("products")
    raw, errors = validate_products(raw)
    check_error_threshold("products", errors)
    prod_key_map, prod_cost_map = load_dim_product(conn, transform_products(raw))
    ctx["product_key_map"] = prod_key_map
    ctx["product_cost_map"] = prod_cost_map

    # ── 4. DimEmployee ───────────────────────────────────────────────────────
    log.info("[ 4/5 ] DimEmployee …")
    raw = download_csv("employees")
    raw, errors = validate_employees(raw)
    check_error_threshold("employees", errors)
    ctx["employee_key_map"] = load_dim_employee(conn, transform_employees(raw))

    # ── 5. DimCampaign ───────────────────────────────────────────────────────
    log.info("[ 5/5 ] DimCampaign …")
    raw = download_csv("campaigns")
    raw, errors = validate_campaigns(raw)
    check_error_threshold("campaigns", errors)
    ctx["campaign_key_map"] = load_dim_campaign(conn, transform_campaigns(raw))
    ctx["campaigns_raw"] = raw   # Reuse for FactCampaignPerformance

    log.info("✓ All dimension tables loaded.")
    return ctx


def run_fact_sales(conn, ctx: dict, watermark: datetime, full_reload: bool) -> int:
    """
    Load FactSales from orders.csv + order_items.csv.
    Incremental: only orders with order_date > watermark are loaded.
    """
    log.info("[ 6/8 ] FactSales …")
    import pandas as pd

    orders_df = ctx["orders_raw"].copy()

    # Apply watermark filter for incremental loads
    if not full_reload:
        orders_df["order_date_parsed"] = pd.to_datetime(orders_df["order_date"], errors="coerce")
        before = len(orders_df)
        orders_df = orders_df[orders_df["order_date_parsed"] > pd.Timestamp(watermark)]
        log.info("  Watermark filter: %d → %d orders (after %s)", before, len(orders_df), watermark)
        if orders_df.empty:
            log.info("  No new orders since watermark — skipping FactSales.")
            return 0

    orders_df, errors = validate_orders(orders_df)
    check_error_threshold("orders", errors)

    # Download and validate order items
    items_df = download_csv("order_items")
    items_df, errors = validate_order_items(items_df)
    check_error_threshold("order_items", errors)

    # Only keep items that belong to orders we're loading
    order_ids_in_scope = set(orders_df["order_id"].astype(str))
    items_df = items_df[items_df["order_id"].astype(str).isin(order_ids_in_scope)]

    # Transform
    fact_df = transform_fact_sales(
        orders_df=orders_df,
        items_df=items_df,
        customer_key_map=ctx["customer_key_map"],
        product_key_map=ctx["product_key_map"],
        product_cost_map=ctx["product_cost_map"],
        geography_key_map=ctx["geography_key_map"],
    )

    # Load
    inserted = load_fact_sales(conn, fact_df)

    # Update watermark to max order_date in this load
    if inserted > 0:
        import pandas as pd
        max_date = pd.to_datetime(orders_df["order_date"], errors="coerce").max()
        if pd.notna(max_date):
            update_watermark(
                conn, "FactSales",
                last_loaded_at=max_date.to_pydatetime(),
                file_loaded=CSV_FILES["orders"],
                rows_inserted=inserted,
                rows_skipped=errors,
            )
    return inserted


def run_fact_tickets(conn, ctx: dict, watermark: datetime, full_reload: bool) -> int:
    """
    Load FactSupportTickets from support_tickets.csv.
    Incremental: only tickets with created_date > watermark.
    """
    import pandas as pd
    log.info("[ 7/8 ] FactSupportTickets …")

    raw = download_csv("support_tickets")
    raw, errors = validate_support_tickets(raw)
    check_error_threshold("support_tickets", errors)

    if not full_reload:
        raw["created_date_parsed"] = pd.to_datetime(raw["created_date"], errors="coerce")
        before = len(raw)
        raw = raw[raw["created_date_parsed"] > pd.Timestamp(watermark)]
        log.info("  Watermark filter: %d → %d tickets (after %s)", before, len(raw), watermark)
        if raw.empty:
            log.info("  No new tickets since watermark — skipping.")
            return 0

    fact_df = transform_fact_tickets(
        tickets_df=raw,
        customer_key_map=ctx["customer_key_map"],
        employee_key_map=ctx["employee_key_map"],
    )
    inserted = load_fact_tickets(conn, fact_df)

    if inserted > 0:
        max_date = pd.to_datetime(raw["created_date"], errors="coerce").max()
        if pd.notna(max_date):
            update_watermark(
                conn, "FactSupportTickets",
                last_loaded_at=max_date.to_pydatetime(),
                file_loaded=CSV_FILES["support_tickets"],
                rows_inserted=inserted,
                rows_skipped=errors,
            )
    return inserted


def run_fact_campaigns(conn, ctx: dict, watermark: datetime, full_reload: bool) -> int:
    """Load FactCampaignPerformance from campaigns.csv."""
    import pandas as pd
    log.info("[ 8/8 ] FactCampaignPerformance …")

    raw = ctx["campaigns_raw"].copy()

    if not full_reload:
        raw["start_date_parsed"] = pd.to_datetime(raw["start_date"], errors="coerce")
        before = len(raw)
        raw = raw[raw["start_date_parsed"] > pd.Timestamp(watermark)]
        log.info("  Watermark filter: %d → %d campaigns (after %s)", before, len(raw), watermark)
        if raw.empty:
            log.info("  No new campaigns since watermark — skipping.")
            return 0

    fact_df = transform_fact_campaigns(raw, ctx["campaign_key_map"])
    inserted = load_fact_campaign_performance(conn, fact_df)

    if inserted > 0:
        max_date = pd.to_datetime(raw["start_date"], errors="coerce").max()
        if pd.notna(max_date):
            update_watermark(
                conn, "FactCampaignPerformance",
                last_loaded_at=max_date.to_pydatetime(),
                file_loaded=CSV_FILES["campaigns"],
                rows_inserted=inserted,
            )
    return inserted


# ── Main entry point ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="InsightHub ETL — Blob Storage → Azure SQL star schema"
    )
    parser.add_argument(
        "--entity",
        choices=["customers", "products", "employees", "campaigns",
                 "sales", "tickets", "campaign_performance", "all"],
        default="all",
        help="Run a single entity or all (default: all)",
    )
    parser.add_argument(
        "--full-reload",
        action="store_true",
        help="Ignore watermarks and reload all fact table records",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Smoke test only: verify connection and blob files exist",
    )
    args = parser.parse_args()

    start_time = time.time()

    log.info("══════════════════════════════════════════════════")
    log.info("InsightHub ETL Pipeline")
    log.info("  Mode       : %s%s",
             args.entity,
             " [FULL RELOAD]" if args.full_reload else " [INCREMENTAL]")
    log.info("  Started    : %s", datetime.utcnow().isoformat())
    log.info("══════════════════════════════════════════════════")

    # ── Smoke test ────────────────────────────────────────────────────────────
    if args.test:
        log.info("Running smoke test …")
        ok = test_connection()
        log.info("  Azure SQL connection: %s", "✓ OK" if ok else "✗ FAILED")
        blobs = list_raw_blobs()
        for name, filename in CSV_FILES.items():
            found = any(filename in b for b in blobs)
            log.info("  Blob %s: %s", filename, "✓ Found" if found else "✗ MISSING")
        sys.exit(0 if ok else 1)

    # ── Full pipeline ─────────────────────────────────────────────────────────
    try:
        with get_connection() as conn:
            ensure_watermark_table(conn)

            ctx = run_dimensions(conn, args.full_reload)

            # Read watermarks
            wm_sales    = get_watermark(conn, "FactSales")             if not args.full_reload else _EPOCH
            wm_tickets  = get_watermark(conn, "FactSupportTickets")    if not args.full_reload else _EPOCH
            wm_campaigns= get_watermark(conn, "FactCampaignPerformance") if not args.full_reload else _EPOCH

            sales_ins    = run_fact_sales(conn, ctx, wm_sales,    args.full_reload)
            tickets_ins  = run_fact_tickets(conn, ctx, wm_tickets, args.full_reload)
            campaign_ins = run_fact_campaigns(conn, ctx, wm_campaigns, args.full_reload)

    except (ConnectionError, RuntimeError, FileNotFoundError) as exc:
        log.error("ETL pipeline failed: %s", exc)
        sys.exit(1)

    elapsed = time.time() - start_time
    log.info("══════════════════════════════════════════════════")
    log.info("✅  ETL Pipeline complete in %.1f seconds", elapsed)
    log.info("  FactSales rows inserted             : %d", sales_ins)
    log.info("  FactSupportTickets rows inserted    : %d", tickets_ins)
    log.info("  FactCampaignPerformance rows inserted: %d", campaign_ins)
    log.info("══════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
