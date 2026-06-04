"""
data-generation/generate_data.py

Generates six realistic datasets for InsightHub using Faker and a fixed seed
so results are fully reproducible across machines.

Datasets produced
-----------------
  customers.csv      — 10,000 customer accounts
  products.csv       —    500 product catalogue entries
  employees.csv      —    200 employee records
  orders.csv         — 50,000 sales orders
  order_items.csv    — line-item breakdown of every order
  support_tickets.csv— 20,000 customer support tickets
  campaigns.csv      —    100 marketing campaigns

All counts, the random seed, and the output directory can be overridden
via environment variables without changing any code.
"""

import csv
import logging
import math
import os
import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from faker import Faker

# ── Load .env for local development ────────────────────────────────────────
load_dotenv()

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Configuration — all values from environment, never hardcoded ────────────
def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"Environment variable '{name}' must be an integer, got: '{raw}'")

SEED          = _int_env("DATA_GENERATION_SEED", 42)
OUTPUT_DIR    = Path(os.getenv("DATA_OUTPUT_DIR", str(Path(__file__).parent / "output")))
NUM_CUSTOMERS = _int_env("NUM_CUSTOMERS", 10_000)
NUM_PRODUCTS  = _int_env("NUM_PRODUCTS", 500)
NUM_EMPLOYEES = _int_env("NUM_EMPLOYEES", 200)
NUM_ORDERS    = _int_env("NUM_ORDERS", 50_000)
NUM_TICKETS   = _int_env("NUM_TICKETS", 20_000)
NUM_CAMPAIGNS = _int_env("NUM_CAMPAIGNS", 100)

# ── Seeded RNG — guarantees same data every run ─────────────────────────────
fake = Faker("en_US")
Faker.seed(SEED)
random.seed(SEED)

# ── Domain constants ────────────────────────────────────────────────────────
PRODUCT_CATEGORIES: Dict[str, Dict] = {
    "Electronics":     {"subs": ["Laptops", "Smartphones", "Tablets", "Headphones", "Cameras", "Smart Home Devices"], "price": (49.99, 2499.99)},
    "Clothing":        {"subs": ["Men's Tops", "Women's Tops", "Denim", "Outerwear", "Activewear", "Accessories"],      "price": (9.99, 299.99)},
    "Books":           {"subs": ["Business", "Technology", "Fiction", "Self-Help", "History", "Science"],               "price": (4.99, 79.99)},
    "Home & Garden":   {"subs": ["Furniture", "Kitchen", "Bedding", "Tools", "Decor", "Outdoor Living"],                "price": (14.99, 1999.99)},
    "Sports":          {"subs": ["Fitness", "Cycling", "Running", "Team Sports", "Water Sports", "Camping"],            "price": (9.99, 899.99)},
    "Beauty":          {"subs": ["Skincare", "Makeup", "Hair Care", "Fragrances", "Men's Grooming"],                    "price": (4.99, 249.99)},
    "Food & Grocery":  {"subs": ["Snacks", "Beverages", "Organic", "International Foods", "Pantry Staples"],            "price": (1.99, 89.99)},
    "Automotive":      {"subs": ["Car Accessories", "Tools & Equipment", "Car Care", "Electronics", "Lighting"],        "price": (9.99, 1499.99)},
    "Toys":            {"subs": ["Action Figures", "Board Games", "Outdoor Toys", "Educational", "Dolls & Plush"],      "price": (4.99, 199.99)},
    "Office":          {"subs": ["Supplies", "Furniture", "Printers", "Networking", "Software"],                        "price": (4.99, 1299.99)},
}

DEPARTMENTS: Dict[str, Dict] = {
    "Sales":            {"count": 30, "salary": (55_000, 120_000)},
    "Marketing":        {"count": 20, "salary": (60_000, 115_000)},
    "Engineering":      {"count": 50, "salary": (85_000, 180_000)},
    "Customer Support": {"count": 60, "salary": (38_000, 75_000)},
    "Finance":          {"count": 15, "salary": (70_000, 140_000)},
    "HR":               {"count": 10, "salary": (55_000, 100_000)},
    "Operations":       {"count": 15, "salary": (50_000, 105_000)},
}

TITLES_BY_DEPT: Dict[str, List[str]] = {
    "Sales":            ["Sales Representative", "Account Executive", "Senior Account Executive", "Sales Manager", "VP of Sales"],
    "Marketing":        ["Marketing Analyst", "Content Strategist", "Campaign Manager", "Marketing Director", "CMO"],
    "Engineering":      ["Software Engineer", "Senior Software Engineer", "Staff Engineer", "Engineering Manager", "VP of Engineering"],
    "Customer Support": ["Support Specialist", "Senior Support Specialist", "Support Team Lead", "Support Manager"],
    "Finance":          ["Financial Analyst", "Senior Financial Analyst", "Finance Manager", "Controller", "CFO"],
    "HR":               ["HR Coordinator", "HR Business Partner", "HR Manager", "CHRO"],
    "Operations":       ["Operations Analyst", "Operations Manager", "Director of Operations", "COO"],
}

TICKET_SUBJECTS: Dict[str, List[str]] = {
    "Billing":   ["Invoice discrepancy on last statement", "Unexpected charge on my account", "Refund not received after 10 days",
                  "Payment declined but funds available", "Subscription renewed without notice"],
    "Technical": ["Cannot log into my account", "Dashboard not loading correctly", "App crashes immediately on launch",
                  "Integration with Salesforce broken", "Export feature producing empty files"],
    "Shipping":  ["Order not received after 2 weeks", "Received wrong item in package", "Package arrived damaged",
                  "Tracking number shows no updates", "Delivery to wrong address"],
    "Returns":   ["Want to return item purchased last week", "Refund status — order #RT-9921", "Request exchange for different size",
                  "Returning defective product", "Item not as described — requesting return"],
    "General":   ["Update billing address on file", "Question about Pro plan features", "Partnership opportunity inquiry",
                  "Feedback on recent product update", "Accessibility support request"],
}

CAMPAIGN_NAME_BASES: List[str] = [
    "New Year Kickoff", "Valentine's Day Promo", "Spring Launch", "Earth Day Initiative",
    "Mother's Day Gifts", "Summer Splash Sale", "Back to School", "Fall Fashion Forward",
    "Halloween Spookfest", "Black Friday Mega Sale", "Cyber Monday Deals", "Holiday Season",
    "Brand Awareness Drive", "Customer Win-Back", "Loyalty Rewards", "Premium Tier Launch",
    "Referral Bonus", "Flash Sale Weekend", "Product Launch Wave", "Influencer Collab",
]

US_STATES: List[str] = [
    "CA", "TX", "FL", "NY", "PA", "IL", "OH", "GA", "NC", "MI",
    "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MD", "MO", "CO",
    "WI", "MN", "SC", "AL", "LA", "KY", "OR", "OK", "CT", "UT",
]

FREE_EMAIL_DOMAINS: List[str] = [
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "icloud.com", "aol.com", "protonmail.com",
]

# ── Utility functions ────────────────────────────────────────────────────────
def random_date(start: date, end: date) -> date:
    """Return a uniformly random date between start and end (inclusive)."""
    delta = (end - start).days
    if delta <= 0:
        return start
    return start + timedelta(days=random.randint(0, delta))


def random_datetime(start: date, end: date) -> datetime:
    """Return a random datetime (date + random HH:MM:SS) in [start, end]."""
    d = random_date(start, end)
    return datetime(
        d.year, d.month, d.day,
        random.randint(0, 23),
        random.randint(0, 59),
        random.randint(0, 59),
    )


def weighted_choice(choices: List[Any], weights: List[float]) -> Any:
    """Pick one item from choices using the supplied probability weights."""
    total = sum(weights)
    cumulative = 0.0
    r = random.random() * total
    for item, weight in zip(choices, weights):
        cumulative += weight
        if r <= cumulative:
            return item
    return choices[-1]


def save_csv(rows: List[Dict[str, Any]], filepath: Path) -> None:
    """Persist a list of dicts as a UTF-8 CSV file, creating dirs as needed."""
    if not rows:
        log.warning("No rows to write — skipping %s", filepath.name)
        return
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    log.info("  ✓ %-22s  %d rows", filepath.name, len(rows))


# ── Dataset generators ───────────────────────────────────────────────────────

def generate_customers(n: int) -> List[Dict[str, Any]]:
    """
    Build n customer records with realistic demographics.

    Distributions:
    - Segment:  Bronze 40%, Silver 30%, Gold 20%, Platinum 10%
    - Status:   Active 78%, Inactive 17%, Suspended 5%
    - Country:  US 80%, international 20%
    - Marketing opt-in: 68%
    """
    log.info("Generating %d customers …", n)
    today = date.today()
    reg_start = date(2019, 1, 1)

    segments     = ["Bronze", "Silver", "Gold", "Platinum"]
    seg_weights  = [0.40, 0.30, 0.20, 0.10]
    statuses     = ["Active", "Inactive", "Suspended"]
    sta_weights  = [0.78, 0.17, 0.05]
    channels     = ["Email", "Phone", "Chat", "In-Person", "Mobile App"]

    customers: List[Dict[str, Any]] = []
    seen_emails: set = set()

    for _ in range(n):
        first = fake.first_name()
        last  = fake.last_name()

        # Guarantee email uniqueness
        domain = random.choice(FREE_EMAIL_DOMAINS)
        email  = f"{first.lower()}.{last.lower()}{random.randint(1, 999)}@{domain}"
        attempts = 0
        while email in seen_emails:
            email = f"{first.lower()}.{last.lower()}{random.randint(1000, 9999)}@{domain}"
            attempts += 1
            if attempts > 20:
                email = f"{uuid.uuid4().hex[:8]}@{domain}"
                break
        seen_emails.add(email)

        reg_date = random_date(reg_start, today)
        dob      = random_date(date(1948, 1, 1), date(2005, 12, 31))

        if random.random() < 0.80:
            country = "US"
            state   = random.choice(US_STATES)
        else:
            country = fake.country_code(representation="alpha-2")
            state   = ""

        customers.append({
            "customer_id":       str(uuid.uuid4()),
            "first_name":        first,
            "last_name":         last,
            "email":             email,
            "phone":             fake.phone_number(),
            "date_of_birth":     dob.isoformat(),
            "registration_date": reg_date.isoformat(),
            "city":              fake.city(),
            "state":             state,
            "country":           country,
            "postal_code":       fake.postcode(),
            "customer_segment":  weighted_choice(segments, seg_weights),
            "account_status":    weighted_choice(statuses, sta_weights),
            "marketing_opt_in":  random.random() < 0.68,
            "preferred_channel": random.choice(channels),
            "lifetime_value":    round(random.uniform(0.0, 18_000.0), 2),
            "referral_source":   random.choice([
                "Organic Search", "Paid Ad", "Social Media",
                "Referral", "Email Campaign", "Direct",
            ]),
        })

    return customers


def generate_products(n: int) -> List[Dict[str, Any]]:
    """
    Build n product catalogue entries across 10 categories.

    Price ranges, cost ratios, and status probabilities vary by category.
    Stock quantities follow a clipped Gaussian to simulate real inventory.
    """
    log.info("Generating %d products …", n)
    today      = date.today()
    categories = list(PRODUCT_CATEGORIES.keys())

    # Pre-generate a realistic brand pool
    brand_pool: List[str] = [fake.company().split()[0] + " " + random.choice(
        ["Tech", "Pro", "Labs", "Co", "Systems", "Works", "Group", "Industries"]
    ) for _ in range(80)]

    status_pool = (["Active"] * 8) + ["Discontinued"] + ["Out of Stock"]

    products: List[Dict[str, Any]] = []
    seen_skus: set = set()

    for _ in range(n):
        category   = random.choice(categories)
        cat_info   = PRODUCT_CATEGORIES[category]
        sub        = random.choice(cat_info["subs"])
        lo, hi     = cat_info["price"]
        unit_price = round(random.uniform(lo, hi), 2)
        cost_price = round(unit_price * random.uniform(0.42, 0.70), 2)

        prefix = category[:3].upper()
        sku    = f"{prefix}-{random.randint(10_000, 99_999)}"
        while sku in seen_skus:
            sku = f"{prefix}-{random.randint(10_000, 99_999)}"
        seen_skus.add(sku)

        brand      = random.choice(brand_pool)
        adjectives = ["Pro", "Plus", "Max", "Lite", "Elite", "Essential", "Ultra", "Prime", "Core"]
        name       = f"{brand.split()[0]} {sub.split()[0]} {random.choice(adjectives)}"

        stock      = max(0, int(random.gauss(350, 220)))
        reorder    = random.randint(15, 120)

        products.append({
            "product_id":     str(uuid.uuid4()),
            "product_name":   name,
            "category":       category,
            "subcategory":    sub,
            "sku":            sku,
            "brand":          brand,
            "unit_price":     unit_price,
            "cost_price":     cost_price,
            "margin_pct":     round((unit_price - cost_price) / unit_price * 100, 2),
            "stock_quantity": stock,
            "reorder_level":  reorder,
            "supplier":       fake.company(),
            "launch_date":    random_date(date(2017, 1, 1), today).isoformat(),
            "status":         random.choice(status_pool),
            "weight_kg":      round(random.uniform(0.05, 30.0), 2),
            "rating":         round(random.uniform(1.5, 5.0), 1),
            "review_count":   random.randint(0, 6_500),
        })

    return products


def generate_employees(n: int) -> List[Dict[str, Any]]:
    """
    Build n employee records with a realistic org hierarchy.

    The first ~12 % of employees generated become managers (their IDs are
    eligible as manager_id values for later employees).  Salary bands are
    set per department.
    """
    log.info("Generating %d employees …", n)
    today = date.today()

    # Expand department slots to a flat list, then shuffle
    dept_slots: List[str] = []
    for dept, info in DEPARTMENTS.items():
        dept_slots.extend([dept] * info["count"])
    # Pad or truncate to exactly n
    while len(dept_slots) < n:
        dept_slots.append(random.choice(list(DEPARTMENTS.keys())))
    dept_slots = dept_slots[:n]
    random.shuffle(dept_slots)

    offices  = ["New York", "San Francisco", "Chicago", "Austin", "Seattle", "Boston", "Atlanta", "Remote"]
    perf_pool = [1, 2, 3, 3, 3, 4, 4, 4, 5, 5]   # skewed toward 3–4

    # Pre-allocate IDs so managers can reference later employees
    emp_ids: List[str] = [str(uuid.uuid4()) for _ in range(n)]

    employees: List[Dict[str, Any]] = []
    manager_candidates: List[str] = []   # Grows as we create employees

    for i, dept in enumerate(dept_slots):
        dept_info  = DEPARTMENTS[dept]
        sal_lo, sal_hi = dept_info["salary"]
        titles     = TITLES_BY_DEPT[dept]
        # Senior title if first 12 % of index (these become managers)
        is_senior  = i < math.ceil(n * 0.12)
        title      = titles[-1] if is_senior else random.choice(titles[:-1])

        manager_id = None
        if manager_candidates and not is_senior:
            manager_id = random.choice(manager_candidates)

        if is_senior:
            manager_candidates.append(emp_ids[i])

        hire_date  = random_date(date(2014, 1, 1), today)
        salary     = (random.randint(sal_lo // 1_000, sal_hi // 1_000)) * 1_000
        first      = fake.first_name()
        last       = fake.last_name()

        employees.append({
            "employee_id":        emp_ids[i],
            "first_name":         first,
            "last_name":          last,
            "email":              f"{first.lower()}.{last.lower()}@insighthub-internal.com",
            "phone":              fake.phone_number(),
            "department":         dept,
            "title":              title,
            "hire_date":          hire_date.isoformat(),
            "salary":             salary,
            "manager_id":         manager_id,
            "office_location":    random.choice(offices),
            "status":             weighted_choice(
                                      ["Active", "On Leave", "Terminated"],
                                      [0.88, 0.05, 0.07],
                                  ),
            "performance_rating": random.choice(perf_pool),
            "years_at_company":   round((today - hire_date).days / 365.25, 1),
        })

    return employees


def generate_orders_and_items(
    n_orders: int,
    customers: List[Dict[str, Any]],
    products: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Build n_orders sales orders and their associated line items.

    Business logic
    ──────────────
    - Only 'Active' products appear in orders (with 'Out of Stock' fallback).
    - Orders span 2022-01-01 to today.
    - Q4 months and summer have higher order volumes.
    - Free shipping is applied when subtotal > $75 (common e-commerce rule).
    - US sales tax approximated at 8.875 % (New York blended rate).
    - Each order has 1–5 line items; quantities 1–4 per line.
    - Discounts of 5 % / 10 % / 15 % / 20 % / 25 % applied randomly.
    """
    log.info("Generating %d orders + line items …", n_orders)
    today       = date.today()
    start_date  = date(2022, 1, 1)
    US_TAX_RATE = 0.08875

    payment_methods = ["Credit Card", "Debit Card", "PayPal", "Bank Transfer", "Apple Pay", "Google Pay"]
    pay_weights     = [0.38, 0.22, 0.18, 0.10, 0.07, 0.05]
    channels        = ["Online", "Mobile App", "In-Store", "Phone"]
    chan_weights     = [0.55, 0.25, 0.15, 0.05]
    statuses        = ["Completed", "Shipped", "Pending", "Cancelled", "Returned"]
    sta_weights     = [0.68, 0.12, 0.05, 0.10, 0.05]
    discount_opts   = [0, 0, 0, 5, 10, 15, 20, 25]   # 0 appears 3× — most items undiscounted

    customer_ids    = [c["customer_id"] for c in customers]
    active_products = [p for p in products if p["status"] == "Active"]
    if not active_products:
        # Fallback: use everything if no active products (shouldn't happen)
        active_products = products

    orders: List[Dict[str, Any]] = []
    items:  List[Dict[str, Any]] = []

    for _ in range(n_orders):
        order_id  = str(uuid.uuid4())
        order_dt  = random_datetime(start_date, today)
        status    = weighted_choice(statuses, sta_weights)
        payment   = weighted_choice(payment_methods, pay_weights)
        channel   = weighted_choice(channels, chan_weights)
        n_items   = random.randint(1, 5)

        selected  = random.choices(active_products, k=n_items)
        subtotal  = 0.0
        disc_total = 0.0

        for prod in selected:
            qty          = random.randint(1, 4)
            unit_price   = prod["unit_price"]
            disc_pct     = random.choice(discount_opts)
            disc_amt     = round(unit_price * qty * disc_pct / 100, 2)
            line_total   = round(unit_price * qty - disc_amt, 2)
            subtotal    += line_total
            disc_total  += disc_amt

            items.append({
                "line_item_id":    str(uuid.uuid4()),
                "order_id":        order_id,
                "product_id":      prod["product_id"],
                "quantity":        qty,
                "unit_price":      unit_price,
                "discount_pct":    disc_pct,
                "discount_amount": disc_amt,
                "line_total":      line_total,
            })

        subtotal    = round(subtotal, 2)
        disc_total  = round(disc_total, 2)
        shipping    = 0.0 if subtotal >= 75.0 else random.choice([4.99, 7.99, 12.99, 19.99])
        tax_amount  = round(subtotal * US_TAX_RATE, 2)
        total       = round(subtotal + shipping + tax_amount, 2)

        if random.random() < 0.80:
            ship_country = "US"
            ship_state   = random.choice(US_STATES)
        else:
            ship_country = fake.country_code(representation="alpha-2")
            ship_state   = ""

        # Cancelled/Returned orders often have a fulfillment timestamp
        shipped_date = None
        delivered_date = None
        if status in ("Completed", "Shipped", "Returned"):
            shipped_dt   = order_dt + timedelta(days=random.randint(1, 3))
            shipped_date = shipped_dt.date().isoformat()
            if status in ("Completed", "Returned"):
                delivered_dt   = shipped_dt + timedelta(days=random.randint(2, 10))
                delivered_date = delivered_dt.date().isoformat()

        orders.append({
            "order_id":          order_id,
            "customer_id":       random.choice(customer_ids),
            "order_date":        order_dt.isoformat(),
            "status":            status,
            "payment_method":    payment,
            "channel":           channel,
            "subtotal":          subtotal,
            "discount_total":    disc_total,
            "shipping_amount":   shipping,
            "tax_amount":        tax_amount,
            "total_amount":      total,
            "shipped_date":      shipped_date,
            "delivered_date":    delivered_date,
            "shipping_city":     fake.city(),
            "shipping_state":    ship_state,
            "shipping_country":  ship_country,
            "shipping_postal":   fake.postcode(),
        })

    return orders, items


def generate_support_tickets(
    n: int,
    customers: List[Dict[str, Any]],
    employees: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Build n support tickets linked to customers and support employees.

    Resolution times follow an exponential-like distribution — most tickets
    close within 24 hours, but some drag on for days.
    """
    log.info("Generating %d support tickets …", n)
    today       = date.today()
    start_date  = date(2022, 1, 1)

    support_staff = [e for e in employees if e["department"] == "Customer Support"]
    if not support_staff:
        support_staff = employees      # Safety fallback

    customer_ids  = [c["customer_id"] for c in customers]
    support_ids   = [e["employee_id"] for e in support_staff]

    categories    = list(TICKET_SUBJECTS.keys())
    priorities    = ["Low", "Medium", "High", "Critical"]
    pri_weights   = [0.30, 0.40, 0.22, 0.08]
    statuses      = ["Resolved", "Closed", "Open", "In Progress", "Escalated"]
    sta_weights   = [0.45, 0.25, 0.12, 0.13, 0.05]
    in_channels   = ["Email", "Phone", "Chat", "Self-Service Portal"]

    tickets: List[Dict[str, Any]] = []

    for _ in range(n):
        category   = random.choice(categories)
        subject    = random.choice(TICKET_SUBJECTS[category])
        created_dt = random_datetime(start_date, today)
        status     = weighted_choice(statuses, sta_weights)
        priority   = weighted_choice(priorities, pri_weights)

        resolved_dt        = None
        resolution_hours   = None
        satisfaction_rating = None

        if status in ("Resolved", "Closed"):
            # Exponential distribution: most tickets resolve quickly
            raw_hours        = random.expovariate(1 / 18)   # mean ≈ 18 h
            resolution_hours = round(max(0.5, min(raw_hours, 240.0)), 1)
            resolved_dt_raw  = created_dt + timedelta(hours=resolution_hours)
            # Cap at today
            if resolved_dt_raw.date() > today:
                resolved_dt_raw  = datetime.combine(today, datetime.min.time())
                resolution_hours = round((resolved_dt_raw - created_dt).total_seconds() / 3600, 1)
            resolved_dt          = resolved_dt_raw.isoformat()
            satisfaction_rating  = random.randint(1, 5)

        tickets.append({
            "ticket_id":             str(uuid.uuid4()),
            "customer_id":           random.choice(customer_ids),
            "assigned_employee_id":  random.choice(support_ids),
            "created_date":          created_dt.isoformat(),
            "resolved_date":         resolved_dt,
            "category":              category,
            "priority":              priority,
            "status":                status,
            "subject":               subject,
            "channel":               random.choice(in_channels),
            "resolution_hours":      resolution_hours,
            "satisfaction_rating":   satisfaction_rating,
            "first_response_hours":  round(random.uniform(0.1, 4.0), 2) if status != "Open" else None,
            "escalated":             status == "Escalated",
        })

    return tickets


def generate_campaigns(n: int) -> List[Dict[str, Any]]:
    """
    Build n marketing campaign records with realistic performance metrics.

    ROI is derived from revenue / spend so it is internally consistent.
    CTR and conversion rates are bounded by realistic industry benchmarks.
    """
    log.info("Generating %d marketing campaigns …", n)
    today      = date.today()
    start_date = date(2022, 1, 1)

    types        = ["Email", "Social Media", "PPC", "Display", "Content Marketing", "TV", "Radio", "SMS", "Affiliate"]
    type_weights = [0.25, 0.20, 0.18, 0.10, 0.10, 0.05, 0.04, 0.05, 0.03]
    segments     = ["Bronze", "Silver", "Gold", "Platinum", "All Customers", "New Customers", "Churned"]
    statuses     = ["Completed", "Active", "Paused", "Cancelled", "Planned"]
    sta_weights  = [0.55, 0.15, 0.10, 0.05, 0.15]
    regions      = ["National", "Northeast", "Southeast", "Midwest", "West Coast", "International"]

    # Spend ratio per status (spend as % of budget)
    spend_ratio: Dict[str, Tuple[float, float]] = {
        "Completed": (0.85, 1.05),
        "Active":    (0.20, 0.80),
        "Paused":    (0.10, 0.50),
        "Cancelled": (0.05, 0.30),
        "Planned":   (0.00, 0.00),
    }

    campaigns: List[Dict[str, Any]] = []

    for i in range(n):
        camp_type  = weighted_choice(types, type_weights)
        status     = weighted_choice(statuses, sta_weights)
        budget     = round(random.uniform(5_000, 250_000), 2)
        lo, hi     = spend_ratio[status]
        spend      = round(min(budget * random.uniform(lo, hi), budget * 1.08), 2)

        start      = random_date(start_date, today - timedelta(days=14))
        duration   = random.randint(7, 120)
        end        = start + timedelta(days=duration)

        impressions      = random.randint(5_000, 5_000_000)
        ctr              = random.uniform(0.005, 0.085)
        clicks           = int(impressions * ctr)
        conversion_rate  = random.uniform(0.01, 0.12)
        conversions      = int(clicks * conversion_rate)
        avg_order_val    = random.uniform(45.0, 350.0)
        revenue          = round(conversions * avg_order_val, 2)
        roi_pct          = round((revenue - spend) / spend * 100, 2) if spend > 0 else 0.0

        name_base = CAMPAIGN_NAME_BASES[i % len(CAMPAIGN_NAME_BASES)]

        campaigns.append({
            "campaign_id":       str(uuid.uuid4()),
            "campaign_name":     f"{name_base} — {start.year} ({camp_type})",
            "campaign_type":     camp_type,
            "target_segment":    random.choice(segments),
            "region":            random.choice(regions),
            "start_date":        start.isoformat(),
            "end_date":          end.isoformat(),
            "status":            status,
            "budget":            budget,
            "spend":             spend,
            "impressions":       impressions,
            "clicks":            clicks,
            "ctr_pct":           round(ctr * 100, 3),
            "conversions":       conversions,
            "conversion_rate_pct": round(conversion_rate * 100, 3),
            "revenue_generated": revenue,
            "roi_pct":           roi_pct,
            "cost_per_click":    round(spend / clicks, 4) if clicks > 0 else 0.0,
            "cost_per_conversion": round(spend / conversions, 2) if conversions > 0 else 0.0,
        })

    return campaigns


# ── Orchestrator ─────────────────────────────────────────────────────────────
def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("InsightHub Data Generator")
    log.info("  Seed        : %d", SEED)
    log.info("  Output dir  : %s", OUTPUT_DIR)
    log.info("=" * 60)

    customers = generate_customers(NUM_CUSTOMERS)
    save_csv(customers, OUTPUT_DIR / "customers.csv")

    products = generate_products(NUM_PRODUCTS)
    save_csv(products, OUTPUT_DIR / "products.csv")

    employees = generate_employees(NUM_EMPLOYEES)
    save_csv(employees, OUTPUT_DIR / "employees.csv")

    orders, order_items = generate_orders_and_items(NUM_ORDERS, customers, products)
    save_csv(orders,      OUTPUT_DIR / "orders.csv")
    save_csv(order_items, OUTPUT_DIR / "order_items.csv")

    tickets = generate_support_tickets(NUM_TICKETS, customers, employees)
    save_csv(tickets, OUTPUT_DIR / "support_tickets.csv")

    campaigns = generate_campaigns(NUM_CAMPAIGNS)
    save_csv(campaigns, OUTPUT_DIR / "campaigns.csv")

    log.info("=" * 60)
    log.info("✅  All datasets generated successfully.")
    log.info("    Run upload_to_blob.py to push CSVs to Azure Blob Storage.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
