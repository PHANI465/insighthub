"""
etl-pipelines/python-local/transformers.py

Transforms validated DataFrames into the exact column layout expected
by the Azure SQL dimension and fact tables.
"""

import logging
from datetime import datetime, date
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from config import COUNTRY_NAMES, WORLD_REGION

log = logging.getLogger(__name__)


# ── Date key helpers ──────────────────────────────────────────────────────────

def _to_date_key(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed.dt.strftime("%Y%m%d").where(parsed.notna(), other=None).apply(
        lambda x: int(x) if x is not None else None
    )


def _to_date_key_nullable(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    result = []
    for ts in parsed:
        if pd.isna(ts):
            result.append(None)
        else:
            result.append(int(ts.strftime("%Y%m%d")))
    return pd.Series(result, index=series.index)


def _bool_col(series: pd.Series) -> pd.Series:
    return series.map(
        {True: 1, False: 0, "True": 1, "False": 0, "true": 1, "false": 0,
         1: 1, 0: 0, "1": 1, "0": 0}
    ).fillna(0).astype(int)


def _age_group(dob_series: pd.Series) -> pd.Series:
    today = pd.Timestamp.today()
    age = ((today - pd.to_datetime(dob_series, errors="coerce")).dt.days / 365.25)
    bins   = [0, 24, 34, 44, 54, 64, 200]
    labels = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
    return pd.cut(age, bins=bins, labels=labels, right=True).astype(object).where(
        age.notna(), other=None
    )


def _safe_numeric(series: pd.Series, decimals: int = 2, default: float = 0.0) -> pd.Series:
    """
    Safely convert any series to float, replacing all bad values with default.
    Extra safety: converts to Python float explicitly to avoid numpy type
    issues with pyodbc which can cause 'Error converting varchar to numeric'.
    """
    result = pd.to_numeric(series, errors="coerce").fillna(default).round(decimals)
    return result.astype(float)


def _safe_int(series: pd.Series, default: int = 0) -> pd.Series:
    """Safely convert any series to int."""
    return pd.to_numeric(series, errors="coerce").fillna(default).astype(int)


# ── Dimension transformers ────────────────────────────────────────────────────

def transform_customers(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["CustomerID"]        = df["customer_id"].astype(str)
    out["FirstName"]         = df["first_name"].astype(str).str.strip()
    out["LastName"]          = df["last_name"].astype(str).str.strip()
    out["FullName"]          = out["FirstName"] + " " + out["LastName"]
    out["Email"]             = df["email"].astype(str).str.lower().str.strip()
    out["Phone"]             = df["phone"].astype(str).where(df["phone"].notna(), other=None)
    out["DateOfBirth"]       = pd.to_datetime(df["date_of_birth"], errors="coerce").dt.date
    out["AgeGroup"]          = _age_group(df["date_of_birth"])
    out["RegistrationDate"]  = pd.to_datetime(df["registration_date"], errors="coerce").dt.date
    out["CustomerSegment"]   = df["customer_segment"].astype(str).str.strip()
    out["AccountStatus"]     = df["account_status"].astype(str).str.strip()
    out["MarketingOptIn"]    = _bool_col(df["marketing_opt_in"])
    out["PreferredChannel"]  = df["preferred_channel"].astype(str).where(df["preferred_channel"].notna(), other=None)
    out["ReferralSource"]    = df["referral_source"].astype(str).where(df["referral_source"].notna(), other=None)
    out["LifetimeValue"]     = _safe_numeric(df["lifetime_value"], decimals=2)
    log.debug("transform_customers: %d rows", len(out))
    return out


def transform_products(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["ProductID"]      = df["product_id"].astype(str)
    out["ProductName"]    = df["product_name"].astype(str).str.strip().str[:200]
    out["SKU"]            = df["sku"].astype(str).str.strip().str[:50]
    out["Brand"]          = df["brand"].astype(str).str.strip().str[:100]
    out["Category"]       = df["category"].astype(str).str.strip().str[:100]
    out["Subcategory"]    = df["subcategory"].astype(str).str.strip().str[:100]
    out["UnitPrice"]      = _safe_numeric(df["unit_price"],    decimals=2)
    out["CostPrice"]      = _safe_numeric(df["cost_price"],    decimals=2)
    out["MarginPct"]      = _safe_numeric(df["margin_pct"],    decimals=2)
    out["WeightKg"]       = _safe_numeric(df["weight_kg"],     decimals=3)
    out["Supplier"]       = df["supplier"].astype(str).where(df["supplier"].notna(), other=None)
    out["StockQuantity"]  = _safe_int(df["stock_quantity"])
    out["ReorderLevel"]   = _safe_int(df["reorder_level"],  default=50)
    out["LaunchDate"]     = pd.to_datetime(df["launch_date"], errors="coerce").dt.date
    out["ProductStatus"]  = df["status"].astype(str).str.strip().str[:50]
    out["Rating"]         = _safe_numeric(df["rating"],        decimals=1)
    out["ReviewCount"]    = _safe_int(df["review_count"])
    log.debug("transform_products: %d rows", len(out))
    return out


def transform_employees(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["EmployeeID"]         = df["employee_id"].astype(str)
    out["FirstName"]          = df["first_name"].astype(str).str.strip()
    out["LastName"]           = df["last_name"].astype(str).str.strip()
    out["FullName"]           = out["FirstName"] + " " + out["LastName"]
    out["Email"]              = df["email"].astype(str).str.lower().str.strip()
    out["Department"]         = df["department"].astype(str).str.strip()
    out["Title"]              = df["title"].astype(str).str.strip()
    out["HireDate"]           = pd.to_datetime(df["hire_date"], errors="coerce").dt.date
    out["Salary"]             = _safe_int(df["salary"])
    out["ManagerEmployeeID"]  = df["manager_id"].astype(str).where(
                                    df["manager_id"].notna() & (df["manager_id"].astype(str) != "None"),
                                    other=None
                                )
    out["OfficeLocation"]     = df["office_location"].astype(str).where(df["office_location"].notna(), other=None)
    out["EmployeeStatus"]     = df["status"].astype(str).str.strip()
    out["PerformanceRating"]  = _safe_int(df["performance_rating"], default=3)
    today = pd.Timestamp.today()
    hire  = pd.to_datetime(df["hire_date"], errors="coerce")
    out["YearsAtCompany"]     = ((today - hire).dt.days / 365.25).fillna(0).round(1)
    log.debug("transform_employees: %d rows", len(out))
    return out


def transform_campaigns(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["CampaignID"]      = df["campaign_id"].astype(str)
    out["CampaignName"]    = df["campaign_name"].astype(str).str.strip()
    out["CampaignType"]    = df["campaign_type"].astype(str).str.strip()
    out["TargetSegment"]   = df["target_segment"].astype(str).str.strip()
    out["Region"]          = df["region"].astype(str).str.strip()
    start = pd.to_datetime(df["start_date"], errors="coerce")
    end   = pd.to_datetime(df["end_date"],   errors="coerce")
    out["DurationDays"]    = (end - start).dt.days.fillna(0).astype(int)
    out["CampaignStatus"]  = df["status"].astype(str).str.strip()
    log.debug("transform_campaigns: %d rows", len(out))
    return out


def extract_geographies(orders_df: pd.DataFrame) -> pd.DataFrame:
    geo = orders_df[["shipping_city", "shipping_state", "shipping_country", "shipping_postal"]].copy()
    geo.columns = ["City", "StateCode", "Country", "PostalCode"]

    geo["City"] = (
        geo["City"]
        .astype(str).str.strip()
        .replace(["nan", "None", "N/A", "n/a", "NA", ""], "Unknown")
        .fillna("Unknown")
        .str[:100]
    )
    geo["StateCode"] = (
        geo["StateCode"]
        .astype(str).str.strip()
        .replace(["nan", "None", "N/A", "n/a", "NA", ""], "")
        .fillna("")
        .str[:50]
    )
    geo["Country"] = (
        geo["Country"]
        .astype(str).str.strip()
        .replace(["nan", "None", "N/A", "n/a", "NA", ""], "US")
        .fillna("US")
        .str[:10]
    )
    geo["PostalCode"] = (
        geo["PostalCode"]
        .astype(str).str.strip()
        .replace(["nan", "None", "N/A", "n/a", "NA", ""], None)
        .str[:20]
    )
    geo["CountryName"] = geo["Country"].map(COUNTRY_NAMES).fillna("Unknown").str[:100]
    geo["State"]       = geo["StateCode"].str[:100]
    geo["WorldRegion"] = geo["Country"].map(WORLD_REGION).fillna("Other").str[:50]
    geo["IsUSA"]       = (geo["Country"] == "US").astype(int)
    geo = geo.drop_duplicates(subset=["City", "StateCode", "Country", "PostalCode"])
    log.debug("extract_geographies: %d unique combinations", len(geo))
    return geo


# ── Fact transformers ─────────────────────────────────────────────────────────

def transform_fact_sales(
    orders_df: pd.DataFrame,
    items_df: pd.DataFrame,
    customer_key_map: Dict[str, int],
    product_key_map: Dict[str, int],
    product_cost_map: Dict[str, float],
    geography_key_map: Dict[Tuple, int],
) -> pd.DataFrame:
    # 1. Count line items per order (for proration)
    item_count = items_df.groupby("order_id")["line_item_id"].count().rename("line_count")

    # 2. Join items with orders
    df = items_df.merge(orders_df, on="order_id", how="inner")
    df = df.merge(item_count, on="order_id", how="left")
    df["line_count"] = df["line_count"].fillna(1).astype(int)

    # 3. Prorate order-level amounts to each line item
    df["ship_amt"] = pd.to_numeric(df["shipping_amount"], errors="coerce").fillna(0) / df["line_count"]
    df["tax_amt"]  = pd.to_numeric(df["tax_amount"],      errors="coerce").fillna(0) / df["line_count"]
    df["line_total_num"] = pd.to_numeric(df["line_total"], errors="coerce").fillna(0)
    df["gross_revenue"]  = (df["line_total_num"] + df["ship_amt"] + df["tax_amt"]).round(2)

    # 4. Resolve DateKeys
    df["OrderDateKey"]     = _to_date_key(df["order_date"])
    df["ShippedDateKey"]   = _to_date_key_nullable(df["shipped_date"])
    df["DeliveredDateKey"] = _to_date_key_nullable(df["delivered_date"])

    # 5. Resolve FK surrogate keys
    df["CustomerKey"]  = df["customer_id"].astype(str).map(customer_key_map)
    df["ProductKey"]   = df["product_id"].astype(str).map(product_key_map)
    df["cost_price"]   = df["product_id"].astype(str).map(product_cost_map).fillna(0.0)
    df["CostOfGoods"]  = (df["cost_price"] * pd.to_numeric(df["quantity"], errors="coerce").fillna(0)).round(2)
    df["GrossProfit"]  = (df["gross_revenue"] - df["CostOfGoods"]).round(2)

    # 6. Resolve GeographyKey — must match extract_geographies normalization exactly
    _GEO_NULLISH = frozenset({"nan", "None", "N/A", "n/a", "NA", ""})

    def _geo_key(r) -> tuple:
        city = str(r["shipping_city"]).strip()
        city = "Unknown" if city in _GEO_NULLISH else city[:100]
        state = str(r["shipping_state"]).strip()
        state = "" if state in _GEO_NULLISH else state[:50]
        country = str(r["shipping_country"]).strip()
        country = "US" if country in _GEO_NULLISH else country[:10]
        postal_v = r["shipping_postal"]
        if pd.isna(postal_v):
            postal = None
        else:
            postal = str(postal_v).strip()
            postal = None if postal in _GEO_NULLISH else postal[:20]
        return (city, state, country, postal)

    geo_tuple = df[["shipping_city", "shipping_state", "shipping_country", "shipping_postal"]].apply(
        _geo_key, axis=1
    )
    df["GeographyKey"] = geo_tuple.map(geography_key_map)

    # 7. Drop rows where any required FK is NULL
    required_fks = ["OrderDateKey", "CustomerKey", "ProductKey", "GeographyKey"]
    before = len(df)
    df = df.dropna(subset=required_fks)
    dropped = before - len(df)
    if dropped > 0:
        log.warning("  [FactSales] Dropped %d rows with unresolvable FK", dropped)

    # 8. Assemble final staging DataFrame
    out = pd.DataFrame()
    out["OrderDateKey"]      = df["OrderDateKey"].astype(int)
    out["CustomerKey"]       = df["CustomerKey"].astype(int)
    out["ProductKey"]        = df["ProductKey"].astype(int)
    out["GeographyKey"]      = df["GeographyKey"].astype(int)
    out["ShippedDateKey"]    = df["ShippedDateKey"]
    out["DeliveredDateKey"]  = df["DeliveredDateKey"]
    out["OrderID"]           = df["order_id"].astype(str)
    out["LineItemID"]        = df["line_item_id"].astype(str)
    out["OrderStatus"]       = df["status"].astype(str).str.strip()
    out["PaymentMethod"]     = df["payment_method"].astype(str).str.strip()
    out["OrderChannel"]      = df["channel"].astype(str).str.strip()
    out["Quantity"]          = _safe_int(df["quantity"], default=1)
    out["DiscountAmount"]    = _safe_numeric(df["discount_amount"], decimals=2)
    out["LineTotal"]         = df["line_total_num"].round(2)
    out["ShippingAmount"]    = df["ship_amt"].round(2)
    out["TaxAmount"]         = df["tax_amt"].round(2)
    out["GrossRevenue"]      = df["gross_revenue"]
    out["CostOfGoods"]       = df["CostOfGoods"]
    out["GrossProfit"]       = df["GrossProfit"]
    out["UnitPrice"]         = _safe_numeric(df["unit_price"], decimals=2)
    out["DiscountPct"]       = _safe_int(df["discount_pct"])
    log.info("  transform_fact_sales: %d line items ready for load", len(out))
    return out


def transform_fact_tickets(
    tickets_df: pd.DataFrame,
    customer_key_map: Dict[str, int],
    employee_key_map: Dict[str, int],
) -> pd.DataFrame:
    df = tickets_df.copy()
    df["CreatedDateKey"]        = _to_date_key(df["created_date"])
    df["ResolvedDateKey"]       = _to_date_key_nullable(df["resolved_date"])
    df["CustomerKey"]           = df["customer_id"].astype(str).map(customer_key_map)
    df["AssignedEmployeeKey"]   = df["assigned_employee_id"].astype(str).map(employee_key_map)

    before = len(df)
    df = df.dropna(subset=["CreatedDateKey", "CustomerKey"])
    dropped = before - len(df)
    if dropped > 0:
        log.warning("  [FactSupportTickets] Dropped %d rows with null FK", dropped)

    out = pd.DataFrame()
    out["CreatedDateKey"]       = df["CreatedDateKey"].astype(int)
    out["ResolvedDateKey"]      = df["ResolvedDateKey"]
    out["CustomerKey"]          = df["CustomerKey"].astype(int)
    out["AssignedEmployeeKey"]  = df["AssignedEmployeeKey"]
    out["TicketID"]             = df["ticket_id"].astype(str)
    out["Category"]             = df["category"].astype(str).str.strip()
    out["Priority"]             = df["priority"].astype(str).str.strip()
    out["TicketStatus"]         = df["status"].astype(str).str.strip()
    out["InboundChannel"]       = df["channel"].astype(str).str.strip()
    out["ResolutionHours"]      = pd.to_numeric(df["resolution_hours"],     errors="coerce").clip(lower=0).round(1)  # NULL for open tickets; constraint >= 0
    out["SatisfactionRating"]   = pd.to_numeric(df["satisfaction_rating"],  errors="coerce")  # keep NaN → SQL NULL (constraint: 1-5 or NULL)
    out["FirstResponseHours"]   = pd.to_numeric(df["first_response_hours"], errors="coerce").clip(lower=0).round(2)  # NULL-safe; clip negatives
    out["IsEscalated"]          = _bool_col(df["escalated"])
    out["IsResolved"]           = (df["status"].isin({"Resolved", "Closed"})).astype(int)
    log.info("  transform_fact_tickets: %d rows ready for load", len(out))
    return out


def transform_fact_campaigns(
    campaigns_df: pd.DataFrame,
    campaign_key_map: Dict[str, int],
) -> pd.DataFrame:
    df = campaigns_df.copy()
    df["StartDateKey"]   = _to_date_key(df["start_date"])
    df["EndDateKey"]     = _to_date_key(df["end_date"])
    df["CampaignKey"]    = df["campaign_id"].astype(str).map(campaign_key_map)

    before = len(df)
    df = df.dropna(subset=["StartDateKey", "EndDateKey", "CampaignKey"])
    dropped = before - len(df)
    if dropped > 0:
        log.warning("  [FactCampaignPerformance] Dropped %d rows with null FK", dropped)

    start = pd.to_datetime(df["start_date"], errors="coerce")
    end   = pd.to_datetime(df["end_date"],   errors="coerce")

    out = pd.DataFrame()
    out["CampaignKey"]           = df["CampaignKey"].astype(int)
    out["StartDateKey"]          = df["StartDateKey"].astype(int)
    out["EndDateKey"]            = df["EndDateKey"].astype(int)
    out["CampaignID"]            = df["campaign_id"].astype(str)
    out["Budget"]                = _safe_numeric(df["budget"],              decimals=2)
    out["Spend"]                 = _safe_numeric(df["spend"],               decimals=2)
    out["Impressions"]           = _safe_int(df["impressions"])
    out["Clicks"]                = _safe_int(df["clicks"])
    out["Conversions"]           = _safe_int(df["conversions"])
    out["RevenueGenerated"]      = _safe_numeric(df["revenue_generated"],   decimals=2)
    out["DurationDays"]          = ((end - start).dt.days).fillna(0).astype(int)
    out["ROI_Pct"]               = _safe_numeric(df["roi_pct"],             decimals=2)
    out["CTR_Pct"]               = _safe_numeric(df["ctr_pct"],             decimals=3)
    out["ConversionRate_Pct"]    = _safe_numeric(df["conversion_rate_pct"], decimals=3)
    out["CostPerClick"]          = _safe_numeric(df["cost_per_click"],      decimals=4)
    out["CostPerConversion"]     = _safe_numeric(df["cost_per_conversion"],  decimals=2)

    spend_vals  = out["Spend"].values
    budget_vals = out["Budget"].values
    util = np.where(budget_vals > 0, spend_vals / budget_vals * 100, 0.0)
    out["BudgetUtilization_Pct"] = np.round(util, 2)

    log.info("  transform_fact_campaigns: %d rows ready for load", len(out))
    return out
