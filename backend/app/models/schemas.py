"""
backend/app/models/schemas.py

Pydantic request and response schemas for all InsightHub API endpoints.
These schemas define the API contract — what the frontend sends and receives.
"""

from datetime import datetime, date
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, field_validator


# ── Auth schemas ──────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int       # seconds until access token expires
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    user_id: int
    username: str
    email: str
    role: str
    is_active: bool


# ── Metrics schemas ───────────────────────────────────────────────────────────

class DateRangeParams(BaseModel):
    """Query parameters for date-filtered metrics endpoints."""
    from_date: Optional[date] = None
    to_date:   Optional[date] = None
    granularity: str = "month"   # day | week | month | quarter | year

    @field_validator("granularity")
    @classmethod
    def valid_granularity(cls, v: str) -> str:
        allowed = {"day", "week", "month", "quarter", "year"}
        if v not in allowed:
            raise ValueError(f"granularity must be one of {allowed}")
        return v


class KPISummary(BaseModel):
    """Aggregated headline KPIs for the executive dashboard."""
    total_revenue: float
    total_orders: int
    total_customers: int
    avg_order_value: float
    gross_profit: float
    gross_margin_pct: float
    total_tickets: int
    avg_csat: Optional[float]
    open_tickets: int
    total_campaigns: int
    top_campaign_roi_pct: float
    period_label: str


class RevenueTrend(BaseModel):
    """One row in a revenue-over-time chart."""
    period: str         # e.g. 'Jan 2024', 'Q1 2024', '2024-01-15'
    revenue: float
    gross_profit: float
    order_count: int
    avg_order_value: float


class CustomerSegmentStat(BaseModel):
    segment: str
    customer_count: int
    total_revenue: float
    avg_ltv: float
    avg_order_value: float
    churn_risk_count: int      # account_status = 'Inactive'


class ProductPerformanceRow(BaseModel):
    product_id: str
    product_name: str
    category: str
    brand: str
    units_sold: int
    total_revenue: float
    gross_profit: float
    margin_pct: float
    avg_discount_pct: float
    rating: Optional[float]
    stock_qty: int
    needs_reorder: bool


class SupportMetricsRow(BaseModel):
    period: str
    category: str
    priority: str
    total_tickets: int
    resolved_tickets: int
    escalated_tickets: int
    avg_resolution_hours: Optional[float]
    avg_csat: Optional[float]
    sla_compliance_pct: Optional[float]


class CampaignROIRow(BaseModel):
    campaign_name: str
    campaign_type: str
    region: str
    budget: float
    spend: float
    revenue: float
    roi_pct: float
    impressions: int
    clicks: int
    conversions: int
    ctr_pct: float
    conversion_rate_pct: float
    roi_band: str


# ── Search schemas ────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: Optional[Dict[str, Any]] = None

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Search query cannot be empty")
        # Sanitise: truncate to prevent overly long prompts
        return v.strip()[:500]

    @field_validator("top_k")
    @classmethod
    def top_k_range(cls, v: int) -> int:
        if not 1 <= v <= 20:
            raise ValueError("top_k must be between 1 and 20")
        return v


class SearchResultSource(BaseModel):
    document_id: str
    title: str
    excerpt: str
    score: float
    url: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    answer: str
    sources: List[SearchResultSource]
    latency_ms: int


# ── Insights schemas ──────────────────────────────────────────────────────────

class InsightRow(BaseModel):
    """List-view: headline fields only (no raw JSON payloads)."""
    insight_id: str       # UNIQUEIDENTIFIER stored as lowercase UUID string
    category: str         # 'Sales' | 'Customers' | 'Support' | 'Campaigns'
    title: str
    narrative: str
    generated_at: datetime
    period_start: Optional[date]
    period_end: Optional[date]
    confidence_score: Optional[float]


class InsightDetail(InsightRow):
    """
    Detail-view: full insight including the raw GPT-4o structured output
    and the metrics that were fed into the prompt.
    """
    structured_json: Dict[str, Any]    # key_findings, recommendations, risk_flags …
    metrics_json:    Dict[str, Any]    # raw SQL metrics used as prompt context
    model_version:   str
    prompt_tokens:   Optional[int]
    completion_tokens: Optional[int]


class GenerateInsightRequest(BaseModel):
    categories: List[str] = ["Sales", "Customers", "Support", "Campaigns"]
    period_start: Optional[date] = None   # defaults to earliest available data
    period_end:   Optional[date] = None   # defaults to latest available data
    force_refresh: bool = False           # regenerate even if insight already exists

    @field_validator("categories")
    @classmethod
    def valid_categories(cls, v: List[str]) -> List[str]:
        allowed = {"Sales", "Customers", "Support", "Campaigns"}
        invalid = set(v) - allowed
        if invalid:
            raise ValueError(f"Invalid categories: {invalid}. Allowed: {allowed}")
        return v


class GenerateInsightResponse(BaseModel):
    """Response from POST /api/insights/generate."""
    status: str                    # 'completed' | 'partial' | 'failed'
    generated_count: int
    failed_categories: List[str]
    insight_ids: List[str]
    period_start: date
    period_end: date
    total_prompt_tokens: int
    total_completion_tokens: int


# ── Power BI schemas ──────────────────────────────────────────────────────────

class EmbedTokenRequest(BaseModel):
    report_id: Optional[str] = None      # Override default from settings
    workspace_id: Optional[str] = None   # Override default from settings


class EmbedTokenResponse(BaseModel):
    embed_token: str
    embed_url: str
    report_id: str
    workspace_id: str
    expiry: datetime
    token_id: str


# ── Health schema ─────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str           # 'healthy' | 'degraded' | 'unhealthy'
    version: str
    database: str         # 'connected' | 'error: ...'
    timestamp: datetime
