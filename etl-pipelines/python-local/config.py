"""
etl-pipelines/python-local/config.py

Single source of truth for all ETL configuration.
Every value is read from environment variables — nothing is hardcoded.
Fails immediately at import if any required variable is missing, so
operators know exactly what to fix before any data is touched.
"""

import os
from dotenv import load_dotenv

load_dotenv()


# ── Environment helpers ───────────────────────────────────────────────────────
def _require_env(name: str) -> str:
    """Return env var value or raise a clear, actionable error."""
    value = os.getenv(name)
    if not value:
        raise ValueError(
            f"Required environment variable '{name}' is not set. "
            f"Copy .env.example → .env and fill in the value."
        )
    return value


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"Environment variable '{name}' must be an integer, got: '{raw}'")


# ── Azure SQL ─────────────────────────────────────────────────────────────────
DB_SERVER   = _require_env("DB_SERVER")
DB_NAME     = _require_env("DB_NAME")
DB_USER     = _require_env("DB_USER")
DB_PASSWORD = _require_env("DB_PASSWORD")
DB_PORT     = _int_env("DB_PORT", 1433)

# ── Azure Blob Storage ────────────────────────────────────────────────────────
STORAGE_ACCOUNT_NAME = _require_env("STORAGE_ACCOUNT_NAME")
STORAGE_ACCOUNT_KEY  = _require_env("STORAGE_ACCOUNT_KEY")
STORAGE_CONTAINER    = _require_env("STORAGE_CONTAINER")
BLOB_RAW_SUBFOLDER   = os.getenv("BLOB_RAW_SUBFOLDER", "raw/insighthub")

# ── ETL runtime settings ──────────────────────────────────────────────────────
ETL_CHUNK_SIZE = _int_env("ETL_CHUNK_SIZE", 2_000)   # rows per batch commit
ETL_MAX_ERRORS = _int_env("ETL_MAX_ERRORS", 500)     # abort threshold per entity
ETL_LOG_LEVEL  = os.getenv("ETL_LOG_LEVEL", "INFO")

# ── CSV file names (as stored in Blob under BLOB_RAW_SUBFOLDER) ───────────────
CSV_FILES = {
    "customers":        "customers.csv",
    "products":         "products.csv",
    "employees":        "employees.csv",
    "orders":           "orders.csv",
    "order_items":      "order_items.csv",
    "support_tickets":  "support_tickets.csv",
    "campaigns":        "campaigns.csv",
}

# ── Allowed values — must mirror CHECK constraints in schema ──────────────────
VALID_CUSTOMER_SEGMENTS = {"Bronze", "Silver", "Gold", "Platinum"}
VALID_ACCOUNT_STATUSES  = {"Active", "Inactive", "Suspended"}
VALID_PRODUCT_STATUSES  = {"Active", "Discontinued", "Out of Stock"}
VALID_EMPLOYEE_STATUSES = {"Active", "On Leave", "Terminated"}
VALID_ORDER_STATUSES    = {"Completed", "Shipped", "Pending", "Cancelled", "Returned"}
VALID_ORDER_CHANNELS    = {"Online", "Mobile App", "In-Store", "Phone"}
VALID_TICKET_CATEGORIES = {"Billing", "Technical", "Shipping", "Returns", "General"}
VALID_TICKET_PRIORITIES = {"Low", "Medium", "High", "Critical"}
VALID_TICKET_STATUSES   = {"Open", "In Progress", "Resolved", "Closed", "Escalated"}
VALID_CAMPAIGN_TYPES    = {
    "Email", "Social Media", "PPC", "Display",
    "Content Marketing", "TV", "Radio", "SMS", "Affiliate"
}
VALID_CAMPAIGN_STATUSES = {"Completed", "Active", "Paused", "Cancelled", "Planned"}

# ── ISO 3166-1 alpha-2 → Country name (top 50 used in generated data) ────────
COUNTRY_NAMES: dict[str, str] = {
    "US": "United States",       "GB": "United Kingdom",   "CA": "Canada",
    "AU": "Australia",           "DE": "Germany",           "FR": "France",
    "JP": "Japan",               "CN": "China",             "IN": "India",
    "BR": "Brazil",              "MX": "Mexico",            "IT": "Italy",
    "ES": "Spain",               "KR": "South Korea",       "NL": "Netherlands",
    "SE": "Sweden",              "CH": "Switzerland",       "NZ": "New Zealand",
    "SG": "Singapore",           "ZA": "South Africa",      "AR": "Argentina",
    "NG": "Nigeria",             "PH": "Philippines",       "ID": "Indonesia",
    "TH": "Thailand",            "PL": "Poland",            "NO": "Norway",
    "DK": "Denmark",             "FI": "Finland",           "BE": "Belgium",
    "AT": "Austria",             "PT": "Portugal",          "IE": "Ireland",
    "IL": "Israel",              "AE": "United Arab Emirates", "SA": "Saudi Arabia",
    "EG": "Egypt",               "TR": "Turkey",            "MY": "Malaysia",
    "VN": "Vietnam",             "PK": "Pakistan",          "BD": "Bangladesh",
    "NG": "Nigeria",             "KE": "Kenya",             "GH": "Ghana",
    "CO": "Colombia",            "CL": "Chile",             "PE": "Peru",
    "RU": "Russia",              "UA": "Ukraine",
}

# ── World region rollup ───────────────────────────────────────────────────────
WORLD_REGION: dict[str, str] = {
    "US": "North America", "CA": "North America", "MX": "North America",
    "GB": "Europe",  "DE": "Europe",  "FR": "Europe", "IT": "Europe",
    "ES": "Europe",  "NL": "Europe",  "SE": "Europe", "CH": "Europe",
    "PL": "Europe",  "NO": "Europe",  "DK": "Europe", "FI": "Europe",
    "BE": "Europe",  "AT": "Europe",  "PT": "Europe", "IE": "Europe",
    "RU": "Europe",  "UA": "Europe",
    "JP": "Asia Pacific", "CN": "Asia Pacific", "IN": "Asia Pacific",
    "AU": "Asia Pacific", "KR": "Asia Pacific", "SG": "Asia Pacific",
    "NZ": "Asia Pacific", "ID": "Asia Pacific", "TH": "Asia Pacific",
    "PH": "Asia Pacific", "MY": "Asia Pacific", "VN": "Asia Pacific",
    "BD": "Asia Pacific", "PK": "Asia Pacific",
    "BR": "Latin America", "AR": "Latin America", "CO": "Latin America",
    "CL": "Latin America", "PE": "Latin America",
    "AE": "Middle East", "SA": "Middle East", "IL": "Middle East",
    "TR": "Middle East", "EG": "Middle East",
    "ZA": "Africa", "NG": "Africa", "KE": "Africa", "GH": "Africa",
}
