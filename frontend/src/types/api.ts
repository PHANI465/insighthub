// TypeScript interfaces matching the FastAPI Pydantic schemas in
// backend/app/models/schemas.py

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface LoginRequest {
  username: string
  password: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  role: string
}

// ── Metrics ───────────────────────────────────────────────────────────────────

export interface KPISummary {
  total_revenue: number
  total_orders: number
  total_customers: number
  avg_order_value: number
  gross_profit: number
  gross_margin_pct: number
  total_tickets: number
  avg_csat: number | null
  open_tickets: number
  total_campaigns: number
  top_campaign_roi_pct: number
  period_label: string
}

export interface RevenueTrend {
  period: string
  revenue: number
  gross_profit: number
  order_count: number
  avg_order_value: number
}

export interface CustomerSegmentStat {
  segment: string
  customer_count: number
  total_revenue: number
  avg_ltv: number
  avg_order_value: number
  churn_risk_count: number
}

export interface ProductPerformanceRow {
  product_id: string
  product_name: string
  category: string
  brand: string
  units_sold: number
  total_revenue: number
  gross_profit: number
  margin_pct: number
  avg_discount_pct: number
  rating: number | null
  stock_qty: number
  needs_reorder: boolean
}

export interface SupportMetricsRow {
  period: string
  category: string
  priority: string
  total_tickets: number
  resolved_tickets: number
  escalated_tickets: number
  avg_resolution_hours: number | null
  avg_csat: number | null
  sla_compliance_pct: number | null
}

export interface CampaignROIRow {
  campaign_name: string
  campaign_type: string
  region: string
  budget: number
  spend: number
  revenue: number
  roi_pct: number
  impressions: number
  clicks: number
  conversions: number
  ctr_pct: number
  conversion_rate_pct: number
  roi_band: string
}

// ── Search ────────────────────────────────────────────────────────────────────

export interface SearchRequest {
  query: string
  top_k?: number
}

export interface SearchResultSource {
  document_id: string
  title: string
  excerpt: string
  score: number
  url: string | null
}

export interface SearchResponse {
  query: string
  answer: string
  sources: SearchResultSource[]
  latency_ms: number
}

// ── Insights ──────────────────────────────────────────────────────────────────

export interface InsightRow {
  insight_id: string
  category: string
  title: string
  narrative: string
  generated_at: string
  period_start: string | null
  period_end: string | null
  confidence_score: number | null
}

export interface InsightDetail extends InsightRow {
  structured_json: Record<string, unknown>
  metrics_json: Record<string, unknown>
  model_version: string
  prompt_tokens: number | null
  completion_tokens: number | null
}

export interface GenerateInsightRequest {
  categories?: string[]
  period_start?: string
  period_end?: string
  force_refresh?: boolean
}

export interface GenerateInsightResponse {
  status: string
  generated_count: number
  failed_categories: string[]
  insight_ids: string[]
  period_start: string
  period_end: string
  total_prompt_tokens: number
  total_completion_tokens: number
}
