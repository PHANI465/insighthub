"""
backend/app/services/insights_service.py

AI Insights Engine — Phase 7.

Pipeline for each category (Sales | Customers | Support | Campaigns):
  1. MetricsCollector  — focused SQL queries against Azure SQL reporting views
  2. InsightGenerator  — GPT-4o call with engineered prompt; returns structured JSON
  3. InsightStore      — UPSERT result to dbo.AIInsights

Public entry point: run_insight_generation()

── Prompt Engineering Rationale ────────────────────────────────────────────────
1. JSON mode (response_format=json_object): Guarantees parseable output.
   Without it, GPT-4o may wrap JSON in ```json blocks or add preamble prose.
   Constraint: the prompt must contain the word "JSON" (satisfied by all prompts).

2. Temperature 0.2: Factual business analysis needs consistency and precision,
   not creativity. Low temperature → more reproducible, number-anchored output.

3. Metrics in the USER turn, not the system prompt: The system prompt is stable
   across all calls (same role + rules) so it benefits from prompt caching.
   Variable metrics data always flows through the user turn.

4. Explicit JSON schema in every prompt: GPT-4o fills defined fields rather than
   inventing structure. Each field has a name, type annotation, and expected
   range / format. This eliminates hallucinated field names.

5. Concrete analytical rules per category: Instead of "assess churn risk",
   prompts say "Risk level: High if churn_rate > 30%, Medium if 15–30%".
   Rule-based thresholds produce consistent, auditable classifications.

6. Period anchoring: Exact ISO date strings (YYYY-MM-DD) appear in every
   prompt. GPT-4o is instructed to reference the actual period — never say
   "recently" without a date.

7. Confidence score computed in Python, not by GPT-4o: The model cannot
   reliably assess its own output quality. We compute data completeness
   (fraction of expected critical metric fields that are non-null / non-zero).

8. max_tokens=1000: Empirically sufficient for full JSON + narrative
   (typically 700–900 tokens). Too low causes truncated JSON (parse failure).
"""

import json
import logging
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pyodbc
from openai import AzureOpenAI, APIError, RateLimitError

from app.core.config import get_settings
from app.core.database import execute_query

log = logging.getLogger(__name__)

# Suppress httpx transport noise during GPT-4o calls
import logging as _logging
for _n in ("httpx", "httpcore"):
    _logging.getLogger(_n).setLevel(_logging.WARNING)

# ── Constants ─────────────────────────────────────────────────────────────────

_OPENAI_API_VERSION = "2024-02-01"
_TEMPERATURE        = 0.2    # Low entropy for reproducible factual analysis
_MAX_TOKENS         = 1000   # Per insight; 700–900 typically used
_MAX_TREND_POINTS   = 12     # Months of monthly data in prompts
_MAX_CATEGORIES     = 8      # Top product/campaign categories in prompts

# ── System prompt (stable — same for every call) ──────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior business intelligence analyst for InsightHub, a B2C e-commerce analytics platform.

Your role is to transform structured business metrics into executive-quality insights.

Rules you must follow without exception:
1. Base ALL analysis strictly on the metrics supplied in the user message.
   Never invent numbers, trends, or facts not present in the data.
2. If a metric is null or zero, acknowledge the gap — do not speculate.
3. Return ONLY valid JSON matching the exact schema specified in the request.
   Do not add any text before or after the JSON object.
4. Use precise numerical references throughout (e.g. "$1.24M", "12.3%", "847 tickets").
   Never use vague language like "significant" or "recently" without a number or date.
5. The single most important finding must appear first in key_findings.
6. Recommendations must be concrete and directly derived from the supplied metrics,
   not generic best-practice advice.
7. risk_flags: return an empty list [] when no material risks exist.
"""

# ── Metrics Collector ─────────────────────────────────────────────────────────

class MetricsCollector:
    """
    Runs focused SQL queries against Azure SQL reporting views.

    Design: each collect_* method fetches only the columns needed for that
    insight type. This keeps prompt payloads small (fewer tokens) and forces
    clear analytical intent for each category.

    All queries use parameterised ? placeholders — no string interpolation
    of user-controlled values.
    """

    def __init__(self, conn: pyodbc.Connection) -> None:
        self._conn = conn

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _f(v, decimals: int = 2) -> Optional[float]:
        """Safe float cast; returns None for NULL/0."""
        if v is None:
            return None
        return round(float(v), decimals)

    @staticmethod
    def _i(v) -> int:
        return int(v or 0)

    # ── Sales / Revenue ───────────────────────────────────────────────────────

    def collect_sales_metrics(
        self, period_start: date, period_end: date
    ) -> Dict[str, Any]:
        """
        Monthly revenue trend, category breakdown, and period-over-period growth.
        Sources: dbo.vw_SalesSummary (joins FactSales + DimDate + DimCustomer +
                 DimProduct + DimGeography).
        """
        ps, pe = str(period_start), str(period_end)

        # Prior period of the same length (for growth comparison)
        days      = (period_end - period_start).days + 1
        prior_end = period_start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=days - 1)

        trend_rows = execute_query(self._conn, """
            SELECT
                MonthYear,
                CalendarYear,
                MonthNumber,
                SUM(GrossRevenue)           AS Revenue,
                SUM(GrossProfit)            AS GrossProfit,
                COUNT(DISTINCT OrderID)     AS Orders,
                COUNT(DISTINCT CustomerKey) AS UniqueCustomers,
                AVG(GrossRevenue)           AS AvgOrderValue
            FROM dbo.vw_SalesSummary
            WHERE OrderDate BETWEEN ? AND ?
              AND OrderStatus IN ('Completed', 'Shipped')
            GROUP BY MonthYear, CalendarYear, MonthNumber
            ORDER BY CalendarYear, MonthNumber
        """, (ps, pe), fetch="all") or []

        cat_rows = execute_query(self._conn, """
            SELECT TOP (?)
                ProductCategory,
                SUM(GrossRevenue)        AS Revenue,
                SUM(GrossProfit)         AS GrossProfit,
                COUNT(DISTINCT OrderID)  AS Orders
            FROM dbo.vw_SalesSummary
            WHERE OrderDate BETWEEN ? AND ?
              AND OrderStatus IN ('Completed', 'Shipped')
            GROUP BY ProductCategory
            ORDER BY Revenue DESC
        """, (_MAX_CATEGORIES, ps, pe), fetch="all") or []

        cur = execute_query(self._conn, """
            SELECT
                SUM(GrossRevenue)        AS TotalRevenue,
                SUM(GrossProfit)         AS TotalProfit,
                COUNT(DISTINCT OrderID)  AS TotalOrders,
                COUNT(DISTINCT CustomerKey) AS UniqueCustomers,
                AVG(GrossRevenue)        AS AvgOrderValue,
                CASE WHEN SUM(GrossRevenue) > 0
                     THEN SUM(GrossProfit) / SUM(GrossRevenue) * 100
                     ELSE 0 END          AS GrossMarginPct
            FROM dbo.vw_SalesSummary
            WHERE OrderDate BETWEEN ? AND ?
              AND OrderStatus IN ('Completed', 'Shipped')
        """, (ps, pe), fetch="one")

        prior = execute_query(self._conn, """
            SELECT
                SUM(GrossRevenue)        AS PriorRevenue,
                COUNT(DISTINCT OrderID)  AS PriorOrders
            FROM dbo.vw_SalesSummary
            WHERE OrderDate BETWEEN ? AND ?
              AND OrderStatus IN ('Completed', 'Shipped')
        """, (str(prior_start), str(prior_end)), fetch="one")

        cur_rev   = float(cur[0] or 0) if cur else 0.0
        prior_rev = float(prior[0] or 0) if prior else 0.0
        growth    = round((cur_rev - prior_rev) / prior_rev * 100, 2) if prior_rev > 0 else None

        return {
            "period_start":          ps,
            "period_end":            pe,
            "total_revenue":         self._f(cur[0] if cur else 0),
            "total_profit":          self._f(cur[1] if cur else 0),
            "total_orders":          self._i(cur[2] if cur else 0),
            "unique_customers":      self._i(cur[3] if cur else 0),
            "avg_order_value":       self._f(cur[4] if cur else 0),
            "gross_margin_pct":      self._f(cur[5] if cur else 0),
            "prior_period_revenue":  self._f(prior_rev),
            "prior_period_orders":   self._i(prior[1] if prior else 0),
            "revenue_growth_pct":    growth,
            "monthly_trend": [
                {
                    "period":            str(r[0]),
                    "revenue":           self._f(r[3]),
                    "gross_profit":      self._f(r[4]),
                    "orders":            self._i(r[5]),
                    "unique_customers":  self._i(r[6]),
                    "avg_order_value":   self._f(r[7]),
                }
                for r in trend_rows[-_MAX_TREND_POINTS:]
            ],
            "category_breakdown": [
                {
                    "category":     str(r[0]),
                    "revenue":      self._f(r[1]),
                    "gross_profit": self._f(r[2]),
                    "orders":       self._i(r[3]),
                }
                for r in cat_rows
            ],
        }

    # ── Customers / Churn ─────────────────────────────────────────────────────

    def collect_customer_metrics(
        self, period_start: date, period_end: date
    ) -> Dict[str, Any]:
        """
        Customer segment health: counts, LTV, churn status, acquisition, recency.
        Sources: dbo.DimCustomer, dbo.FactSales, dbo.DimDate.
        """
        ps, pe = str(period_start), str(period_end)

        seg_rows = execute_query(self._conn, """
            SELECT
                CustomerSegment,
                COUNT(DISTINCT CustomerKey)                                AS CustomerCount,
                SUM(CASE WHEN AccountStatus = 'Active'   THEN 1 ELSE 0 END) AS ActiveCount,
                SUM(CASE WHEN AccountStatus = 'Inactive' THEN 1 ELSE 0 END) AS ChurnedCount,
                AVG(LifetimeValue)                                         AS AvgLTV,
                SUM(LifetimeValue)                                         AS TotalLTV
            FROM dbo.DimCustomer
            GROUP BY CustomerSegment
            ORDER BY TotalLTV DESC
        """, fetch="all") or []

        new_row = execute_query(self._conn, """
            SELECT COUNT(*) AS NewCustomers
            FROM dbo.DimCustomer
            WHERE RegistrationDate BETWEEN ? AND ?
        """, (ps, pe), fetch="one")

        recency_rows = execute_query(self._conn, """
            SELECT
                dc.CustomerSegment,
                AVG(DATEDIFF(day, dd.FullDate, GETDATE())) AS AvgDaysSinceLast,
                COUNT(DISTINCT dc.CustomerKey)             AS CustomersWithOrders
            FROM dbo.DimCustomer dc
            INNER JOIN (
                SELECT CustomerKey, MAX(OrderDateKey) AS LastKey
                FROM dbo.FactSales
                WHERE OrderStatus NOT IN ('Cancelled')
                GROUP BY CustomerKey
            ) lo ON dc.CustomerKey = lo.CustomerKey
            INNER JOIN dbo.DimDate dd ON lo.LastKey = dd.DateKey
            GROUP BY dc.CustomerSegment
        """, fetch="all") or []

        total_row = execute_query(self._conn, """
            SELECT
                COUNT(*)                                                   AS Total,
                SUM(CASE WHEN AccountStatus = 'Active'   THEN 1 ELSE 0 END) AS Active,
                AVG(LifetimeValue)                                         AS AvgLTV
            FROM dbo.DimCustomer
        """, fetch="one")

        recency = {
            str(r[0]): {"avg_days": self._f(r[1], 1), "with_orders": self._i(r[2])}
            for r in recency_rows
        }

        total    = self._i(total_row[0] if total_row else 0)
        active   = self._i(total_row[1] if total_row else 0)
        churned  = total - active

        segments = []
        for r in seg_rows:
            seg   = str(r[0])
            count = self._i(r[1])
            churn = self._i(r[3])
            segments.append({
                "segment":                   seg,
                "customer_count":            count,
                "active_count":              self._i(r[2]),
                "churned_count":             churn,
                "churn_rate_pct":            round(churn / max(count, 1) * 100, 2),
                "avg_ltv":                   self._f(r[4]),
                "total_ltv":                 self._f(r[5]),
                "avg_days_since_last_order": recency.get(seg, {}).get("avg_days"),
            })

        return {
            "period_start":           ps,
            "period_end":             pe,
            "total_customers":        total,
            "active_customers":       active,
            "churned_customers":      churned,
            "overall_churn_rate_pct": round(churned / max(total, 1) * 100, 2),
            "overall_avg_ltv":        self._f(total_row[2] if total_row else 0),
            "new_customers_in_period": self._i(new_row[0] if new_row else 0),
            "segments":               segments,
        }

    # ── Support Tickets ───────────────────────────────────────────────────────

    def collect_support_metrics(
        self, period_start: date, period_end: date
    ) -> Dict[str, Any]:
        """
        Support ticket patterns: volume, resolution quality, CSAT, escalation.
        Sources: dbo.FactSupportTickets, dbo.DimDate.
        """
        ps, pe = str(period_start), str(period_end)
        params = (ps, pe)

        overall = execute_query(self._conn, """
            SELECT
                COUNT(fst.TicketKey)                                           AS Total,
                SUM(CAST(fst.IsResolved AS INT))                               AS Resolved,
                SUM(CAST(fst.IsEscalated AS INT))                              AS Escalated,
                SUM(CASE WHEN fst.TicketStatus IN ('Open','In Progress')
                         THEN 1 ELSE 0 END)                                    AS Open,
                AVG(fst.ResolutionHours)                                       AS AvgResHours,
                AVG(fst.FirstResponseHours)                                    AS AvgFirstRespHours,
                AVG(CAST(fst.SatisfactionRating AS FLOAT))                     AS AvgCSAT,
                CAST(SUM(CASE WHEN fst.ResolutionHours <= 24 AND fst.IsResolved = 1
                              THEN 1 ELSE 0 END) AS FLOAT)
                    / NULLIF(SUM(CAST(fst.IsResolved AS INT)), 0) * 100        AS SLA24h_Pct
            FROM dbo.FactSupportTickets fst
            INNER JOIN dbo.DimDate cd ON fst.CreatedDateKey = cd.DateKey
            WHERE cd.FullDate BETWEEN ? AND ?
        """, params, fetch="one")

        cat_rows = execute_query(self._conn, """
            SELECT
                fst.Category,
                COUNT(fst.TicketKey)                    AS Tickets,
                SUM(CAST(fst.IsResolved AS INT))        AS Resolved,
                SUM(CAST(fst.IsEscalated AS INT))       AS Escalated,
                AVG(fst.ResolutionHours)                AS AvgResHours,
                AVG(CAST(fst.SatisfactionRating AS FLOAT)) AS AvgCSAT
            FROM dbo.FactSupportTickets fst
            INNER JOIN dbo.DimDate cd ON fst.CreatedDateKey = cd.DateKey
            WHERE cd.FullDate BETWEEN ? AND ?
            GROUP BY fst.Category
            ORDER BY Tickets DESC
        """, params, fetch="all") or []

        pri_rows = execute_query(self._conn, """
            SELECT
                fst.Priority,
                COUNT(fst.TicketKey)                    AS Tickets,
                AVG(fst.ResolutionHours)                AS AvgResHours,
                SUM(CAST(fst.IsEscalated AS INT))       AS Escalated
            FROM dbo.FactSupportTickets fst
            INNER JOIN dbo.DimDate cd ON fst.CreatedDateKey = cd.DateKey
            WHERE cd.FullDate BETWEEN ? AND ?
            GROUP BY fst.Priority
            ORDER BY Tickets DESC
        """, params, fetch="all") or []

        total    = self._i(overall[0] if overall else 0)
        resolved = self._i(overall[1] if overall else 0)
        escalated = self._i(overall[2] if overall else 0)

        return {
            "period_start":             ps,
            "period_end":               pe,
            "total_tickets":            total,
            "resolved_tickets":         resolved,
            "escalated_tickets":        escalated,
            "open_tickets":             self._i(overall[3] if overall else 0),
            "resolution_rate_pct":      round(resolved / max(total, 1) * 100, 2),
            "escalation_rate_pct":      round(escalated / max(total, 1) * 100, 2),
            "avg_resolution_hours":     self._f(overall[4] if overall else None, 1),
            "avg_first_response_hours": self._f(overall[5] if overall else None, 2),
            "avg_csat":                 self._f(overall[6] if overall else None),
            "sla24h_compliance_pct":    self._f(overall[7] if overall else None, 2),
            "by_category": [
                {
                    "category":            str(r[0]),
                    "tickets":             self._i(r[1]),
                    "resolved":            self._i(r[2]),
                    "escalated":           self._i(r[3]),
                    "resolution_rate_pct": round(self._i(r[2]) / max(self._i(r[1]), 1) * 100, 2),
                    "avg_resolution_hours": self._f(r[4], 1),
                    "avg_csat":            self._f(r[5]),
                }
                for r in cat_rows
            ],
            "by_priority": [
                {
                    "priority":             str(r[0]),
                    "tickets":              self._i(r[1]),
                    "avg_resolution_hours": self._f(r[2], 1),
                    "escalated":            self._i(r[3]),
                }
                for r in pri_rows
            ],
        }

    # ── Campaigns ─────────────────────────────────────────────────────────────

    def collect_campaign_metrics(
        self, period_start: date, period_end: date
    ) -> Dict[str, Any]:
        """
        Campaign performance: ROI, spend efficiency, engagement by type.
        Sources: dbo.vw_CampaignROI (joins FactCampaignPerformance + DimCampaign + DimDate).
        The date filter catches campaigns that started OR ended within the period.
        """
        ps, pe = str(period_start), str(period_end)
        # Both StartDate and EndDate filters — use 4 params (2 for each OR branch)
        params = (ps, pe, ps, pe)

        overall = execute_query(self._conn, """
            SELECT
                COUNT(*)                    AS TotalCampaigns,
                SUM(Budget)                 AS TotalBudget,
                SUM(ActualSpend)            AS TotalSpend,
                SUM(RevenueGenerated)       AS TotalRevenue,
                AVG(ROI_Pct)                AS AvgROI,
                MAX(ROI_Pct)                AS BestROI,
                MIN(ROI_Pct)                AS WorstROI,
                SUM(Impressions)            AS TotalImpressions,
                SUM(Clicks)                 AS TotalClicks,
                SUM(Conversions)            AS TotalConversions,
                AVG(CTR_Pct)               AS AvgCTR,
                AVG(ConversionRate_Pct)    AS AvgConvRate
            FROM dbo.vw_CampaignROI
            WHERE StartDate BETWEEN ? AND ?
               OR EndDate   BETWEEN ? AND ?
        """, params, fetch="one")

        type_rows = execute_query(self._conn, """
            SELECT
                CampaignType,
                COUNT(*)                 AS Campaigns,
                AVG(ROI_Pct)             AS AvgROI,
                SUM(RevenueGenerated)    AS TotalRevenue,
                SUM(ActualSpend)         AS TotalSpend,
                AVG(CTR_Pct)            AS AvgCTR,
                AVG(ConversionRate_Pct) AS AvgConvRate
            FROM dbo.vw_CampaignROI
            WHERE StartDate BETWEEN ? AND ?
               OR EndDate   BETWEEN ? AND ?
            GROUP BY CampaignType
            ORDER BY AvgROI DESC
        """, params, fetch="all") or []

        band_rows = execute_query(self._conn, """
            SELECT ROI_Band, COUNT(*) AS Campaigns
            FROM dbo.vw_CampaignROI
            WHERE StartDate BETWEEN ? AND ?
               OR EndDate   BETWEEN ? AND ?
            GROUP BY ROI_Band
        """, params, fetch="all") or []

        total_spend   = float(overall[2] or 0) if overall else 0.0
        total_budget  = float(overall[1] or 0) if overall else 0.0
        total_revenue = float(overall[3] or 0) if overall else 0.0
        net_roi = round((total_revenue - total_spend) / max(total_spend, 1) * 100, 2) if total_spend > 0 else 0.0
        util    = round(total_spend / max(total_budget, 1) * 100, 2) if total_budget > 0 else 0.0

        return {
            "period_start":            ps,
            "period_end":              pe,
            "total_campaigns":         self._i(overall[0] if overall else 0),
            "total_budget":            self._f(total_budget),
            "total_spend":             self._f(total_spend),
            "total_revenue_generated": self._f(total_revenue),
            "net_roi_pct":             net_roi,
            "avg_roi_pct":             self._f(overall[4] if overall else 0),
            "best_roi_pct":            self._f(overall[5] if overall else 0),
            "worst_roi_pct":           self._f(overall[6] if overall else 0),
            "budget_utilization_pct":  util,
            "total_impressions":       self._i(overall[7] if overall else 0),
            "total_clicks":            self._i(overall[8] if overall else 0),
            "total_conversions":       self._i(overall[9] if overall else 0),
            "avg_ctr_pct":             self._f(overall[10] if overall else 0, 3),
            "avg_conversion_rate_pct": self._f(overall[11] if overall else 0, 3),
            "by_type": [
                {
                    "campaign_type":           str(r[0]),
                    "campaigns":               self._i(r[1]),
                    "avg_roi_pct":             self._f(r[2]),
                    "total_revenue":           self._f(r[3]),
                    "total_spend":             self._f(r[4]),
                    "avg_ctr_pct":             self._f(r[5], 3),
                    "avg_conversion_rate_pct": self._f(r[6], 3),
                }
                for r in type_rows
            ],
            "roi_distribution": {str(r[0]): self._i(r[1]) for r in band_rows},
        }


# ── Insight Generator ─────────────────────────────────────────────────────────

class InsightGenerator:
    """
    Calls GPT-4o to produce structured insights from collected metrics.

    Each category has its own prompt method that:
    - Provides all relevant metrics as compact JSON in the user message
    - Specifies the exact JSON output schema (field names, types, constraints)
    - Adds category-specific analytical rules (thresholds, risk criteria)

    The generator returns:  (structured_dict, prompt_tokens, completion_tokens)
    """

    def __init__(self, client: AzureOpenAI, model: str) -> None:
        self._client = client
        self._model  = model

    def _call(self, user_prompt: str) -> Tuple[Dict[str, Any], int, int]:
        """
        Execute one GPT-4o call with JSON mode.
        Raises ValueError if the response is not valid JSON.
        """
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
        )
        raw = response.choices[0].message.content.strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            # Log first 500 chars for debugging without dumping entire response
            log.error("GPT-4o returned non-JSON. First 500 chars: %s", raw[:500])
            raise ValueError(f"GPT-4o response was not valid JSON: {exc}") from exc

        pt = response.usage.prompt_tokens     if response.usage else 0
        ct = response.usage.completion_tokens if response.usage else 0
        return parsed, pt, ct

    # ── Category-specific prompts ─────────────────────────────────────────────

    def generate_sales_insight(self, metrics: Dict) -> Tuple[Dict, int, int]:
        """
        Revenue performance insight.
        Covers: trend direction, category mix, gross margin, MoM growth.
        """
        prompt = f"""
Analyse the revenue and sales performance for InsightHub (B2C e-commerce platform).
Period: {metrics['period_start']} to {metrics['period_end']}

METRICS (JSON):
{json.dumps(metrics, indent=2)}

Return ONLY a JSON object with this EXACT schema — no extra fields, no wrapper text:
{{
  "title": "<executive title, max 80 chars, e.g. 'Q3 2025 Revenue: 14.2% Growth Driven by Electronics'>",
  "narrative": "<2–3 paragraph executive summary. Cover: overall revenue health with exact figures, primary growth driver, margin trend, and one forward-looking risk or opportunity.>",
  "key_findings": [
    "<Finding 1 — must be the most impactful; include a specific $ or % figure>",
    "<Finding 2>",
    "<Finding 3>"
  ],
  "revenue_trend_direction": "growing" | "declining" | "stable",
  "revenue_growth_pct": <number | null>,
  "gross_margin_pct": <number>,
  "top_category": "<category name with highest revenue>",
  "top_category_revenue": <number>,
  "top_category_revenue_share_pct": <number>,
  "recommendations": [
    "<Specific action to sustain or improve revenue — cite the metric that motivates it>",
    "<Second specific action>"
  ],
  "risk_flags": ["<risk description if material, else omit entry>"]
}}

Analytical rules:
- revenue_trend_direction: 'growing' if revenue_growth_pct > 3%, 'declining' if < -3%, else 'stable'.
- top_category_revenue_share_pct = top_category_revenue / total_revenue * 100.
- If monthly_trend has ≥ 3 data points, comment on the trajectory (accelerating / decelerating).
- If gross_margin_pct < 20%, flag it as a risk.
- If a single category > 40% of revenue, flag concentration risk.
"""
        return self._call(prompt)

    def generate_churn_insight(self, metrics: Dict) -> Tuple[Dict, int, int]:
        """
        Customer churn and retention insight.
        Covers: segment-level churn rates, LTV, recency, acquisition.
        """
        prompt = f"""
Analyse customer health and churn risk for InsightHub.
Period for new customer acquisition: {metrics['period_start']} to {metrics['period_end']}

METRICS (JSON):
{json.dumps(metrics, indent=2)}

Return ONLY a JSON object with this EXACT schema:
{{
  "title": "<executive title, max 80 chars, e.g. 'Customer Health: Bronze Segment Shows 38% Churn Risk'>",
  "narrative": "<2–3 paragraph summary. Cover: overall retention rate, which segment is most at risk and why (cite avg_days_since_last_order if available), LTV by segment, and acquisition trend.>",
  "key_findings": [
    "<Finding 1 — most critical churn signal with segment name and exact rate>",
    "<Finding 2 — LTV or acquisition insight>",
    "<Finding 3>"
  ],
  "overall_churn_rate_pct": <number>,
  "highest_churn_segment": "<segment name>",
  "highest_churn_rate_pct": <number>,
  "lowest_churn_segment": "<segment name>",
  "new_customers_acquired": <number>,
  "segments_summary": [
    {{
      "segment": "<name>",
      "customer_count": <number>,
      "churn_rate_pct": <number>,
      "avg_ltv": <number>,
      "avg_days_since_last_order": <number | null>,
      "risk_level": "Low" | "Medium" | "High"
    }}
  ],
  "recommendations": [
    "<Retention action targeting the highest-churn segment — cite specific metric>",
    "<Action to improve acquisition or grow LTV in a specific segment>"
  ],
  "risk_flags": ["<risk description if material, else omit entry>"]
}}

Analytical rules:
- risk_level: 'High' if churn_rate_pct > 30%, 'Medium' if 15–30%, 'Low' if < 15%.
- Flag as risk if the highest-value segment (highest avg_ltv) also has churn_rate > 20%.
- avg_days_since_last_order > 90 is a significant re-engagement signal; cite it explicitly.
- If new_customers_acquired < 1% of total_customers, flag acquisition as lagging.
"""
        return self._call(prompt)

    def generate_support_insight(self, metrics: Dict) -> Tuple[Dict, int, int]:
        """
        Support ticket pattern insight.
        Covers: resolution quality, CSAT, escalation hot spots, SLA compliance.
        """
        prompt = f"""
Analyse customer support operations for InsightHub.
Period: {metrics['period_start']} to {metrics['period_end']}

METRICS (JSON):
{json.dumps(metrics, indent=2)}

Return ONLY a JSON object with this EXACT schema:
{{
  "title": "<executive title, max 80 chars, e.g. 'Support Q3: 23% Escalation Rate in Billing Requires Action'>",
  "narrative": "<2–3 paragraph summary. Cover: overall volume and resolution quality, which category has the worst CSAT or highest escalation (cite exact numbers), SLA compliance, and first-response performance.>",
  "key_findings": [
    "<Finding 1 — highest-impact issue (worst CSAT or highest escalation) with exact figures>",
    "<Finding 2>",
    "<Finding 3>"
  ],
  "resolution_rate_pct": <number>,
  "avg_csat": <number | null>,
  "sla_compliance_pct": <number | null>,
  "escalation_rate_pct": <number>,
  "worst_category_by_csat": "<category name or null>",
  "worst_category_csat": <number | null>,
  "highest_escalation_category": "<category name>",
  "category_summary": [
    {{
      "category": "<name>",
      "tickets": <number>,
      "resolution_rate_pct": <number>,
      "avg_csat": <number | null>,
      "escalation_rate_pct": <number>,
      "concern_level": "Low" | "Medium" | "High"
    }}
  ],
  "recommendations": [
    "<Specific operational improvement targeting the worst-performing category>",
    "<Specific process or staffing recommendation based on volume or SLA data>"
  ],
  "risk_flags": ["<risk if material — e.g. SLA < 70% or CSAT < 3.0>"]
}}

Analytical rules:
- concern_level: 'High' if resolution_rate_pct < 70% OR avg_csat < 3.0.
                 'Medium' if resolution_rate_pct 70–85% OR avg_csat 3.0–3.5. 'Low' otherwise.
- escalation_rate_pct for category = escalated / tickets * 100.
- Risk flag if overall escalation_rate_pct > 15%.
- Risk flag if avg_csat < 3.5 overall.
- Risk flag if sla24h_compliance_pct < 70%.
"""
        return self._call(prompt)

    def generate_campaign_insight(self, metrics: Dict) -> Tuple[Dict, int, int]:
        """
        Campaign effectiveness insight.
        Covers: ROI by type, spend efficiency, conversion performance.
        """
        prompt = f"""
Analyse marketing campaign performance for InsightHub.
Period: {metrics['period_start']} to {metrics['period_end']}

METRICS (JSON):
{json.dumps(metrics, indent=2)}

Return ONLY a JSON object with this EXACT schema:
{{
  "title": "<executive title, max 80 chars, e.g. 'Campaign ROI: Email Outperforms at 312%, Social Lags at 8%'>",
  "narrative": "<2–3 paragraph summary. Cover: overall marketing ROI and revenue contribution, best and worst performing campaign types (cite exact ROI %), budget utilisation, and conversion efficiency.>",
  "key_findings": [
    "<Finding 1 — best vs. worst ROI with exact campaign type names and percentages>",
    "<Finding 2 — conversion or engagement insight>",
    "<Finding 3>"
  ],
  "net_roi_pct": <number>,
  "budget_utilization_pct": <number>,
  "best_campaign_type": "<type name>",
  "best_campaign_type_roi_pct": <number>,
  "worst_campaign_type": "<type name>",
  "worst_campaign_type_roi_pct": <number>,
  "total_conversions": <number>,
  "avg_conversion_rate_pct": <number>,
  "roi_distribution": {{"Excellent": <n>, "Good": <n>, "Break-Even": <n>, "Loss": <n>}},
  "recommendations": [
    "<Budget reallocation or channel recommendation — cite the ROI gap>",
    "<Conversion-rate optimisation suggestion — cite avg_conversion_rate or CTR>"
  ],
  "risk_flags": ["<risk if material>"]
}}

Analytical rules:
- net_roi_pct = (total_revenue_generated - total_spend) / total_spend * 100 (use supplied value).
- budget_utilization_pct = total_spend / total_budget * 100 (use supplied value).
- Risk flag if Loss band campaigns > 25% of total_campaigns.
- Risk flag if avg_conversion_rate_pct < 2%.
- Risk flag if budget_utilization_pct < 50% (underspend) OR > 110% (overspend).
"""
        return self._call(prompt)


# ── Insight Store ─────────────────────────────────────────────────────────────

class InsightStore:
    """
    Persists generated insights to dbo.AIInsights and retrieves them.
    Uses direct cursor access for DDL and DML; execute_query for SELECT.
    """

    def __init__(self, conn: pyodbc.Connection) -> None:
        self._conn = conn

    def ensure_table(self) -> None:
        """
        Create dbo.AIInsights and its indexes if they do not yet exist.
        Safe to call on every generation run (all statements are idempotent).
        """
        cur = self._conn.cursor()
        try:
            cur.execute("""
                IF OBJECT_ID('dbo.AIInsights', 'U') IS NULL
                CREATE TABLE dbo.AIInsights (
                    InsightID        UNIQUEIDENTIFIER  NOT NULL DEFAULT NEWID(),
                    Category         VARCHAR(50)       NOT NULL,
                    Title            VARCHAR(200)      NOT NULL,
                    Narrative        NVARCHAR(MAX)     NOT NULL,
                    StructuredJson   NVARCHAR(MAX)     NOT NULL,
                    MetricsJson      NVARCHAR(MAX)     NOT NULL,
                    PeriodStart      DATE              NOT NULL,
                    PeriodEnd        DATE              NOT NULL,
                    GeneratedAt      DATETIME2(0)      NOT NULL DEFAULT GETUTCDATE(),
                    ConfidenceScore  DECIMAL(4,3)      NULL,
                    ModelVersion     VARCHAR(50)       NOT NULL DEFAULT 'gpt-4o',
                    PromptTokens     INT               NULL,
                    CompletionTokens INT               NULL,
                    CONSTRAINT PK_AIInsights PRIMARY KEY (InsightID),
                    CONSTRAINT CK_AIInsights_Category CHECK (
                        Category IN ('Sales','Customers','Support','Campaigns')
                    )
                )
            """)
            cur.execute("""
                IF NOT EXISTS (
                    SELECT 1 FROM sys.indexes
                    WHERE name = 'IX_AIInsights_Category_GeneratedAt'
                      AND object_id = OBJECT_ID('dbo.AIInsights')
                )
                CREATE NONCLUSTERED INDEX IX_AIInsights_Category_GeneratedAt
                    ON dbo.AIInsights (Category ASC, GeneratedAt DESC)
            """)
            cur.execute("""
                IF NOT EXISTS (
                    SELECT 1 FROM sys.indexes
                    WHERE name = 'IX_AIInsights_Period'
                      AND object_id = OBJECT_ID('dbo.AIInsights')
                )
                CREATE NONCLUSTERED INDEX IX_AIInsights_Period
                    ON dbo.AIInsights (PeriodStart ASC, PeriodEnd ASC)
            """)
            self._conn.commit()
        finally:
            cur.close()

    def insight_exists(
        self, category: str, period_start: date, period_end: date
    ) -> bool:
        """True if an insight for this category + period already exists."""
        row = execute_query(self._conn, """
            SELECT TOP 1 InsightID FROM dbo.AIInsights
            WHERE Category = ? AND PeriodStart = ? AND PeriodEnd = ?
        """, (category, str(period_start), str(period_end)), fetch="one")
        return row is not None

    def save(
        self,
        *,
        category: str,
        title: str,
        narrative: str,
        structured: Dict,
        metrics: Dict,
        period_start: date,
        period_end: date,
        confidence: float,
        model_version: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> str:
        """INSERT one insight row. Returns the new InsightID (lowercase UUID string)."""
        insight_id = str(uuid.uuid4())
        cur = self._conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO dbo.AIInsights (
                    InsightID, Category, Title, Narrative,
                    StructuredJson, MetricsJson,
                    PeriodStart, PeriodEnd,
                    ConfidenceScore, ModelVersion,
                    PromptTokens, CompletionTokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    insight_id,
                    category,
                    title[:200],
                    narrative,
                    json.dumps(structured, ensure_ascii=False),
                    json.dumps(metrics,    ensure_ascii=False),
                    str(period_start),
                    str(period_end),
                    round(confidence, 3),
                    model_version,
                    prompt_tokens,
                    completion_tokens,
                ),
            )
            self._conn.commit()
        finally:
            cur.close()
        return insight_id

    def fetch_list(
        self,
        limit: int = 20,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return recent insights as a list of dicts (no StructuredJson/MetricsJson)."""
        sql  = "SELECT TOP (?) InsightID, Category, Title, Narrative, GeneratedAt, PeriodStart, PeriodEnd, ConfidenceScore FROM dbo.AIInsights WHERE 1=1"
        params: list = [limit]
        if category:
            sql += " AND Category = ?"
            params.append(category)
        sql += " ORDER BY GeneratedAt DESC"
        rows = execute_query(self._conn, sql, tuple(params), fetch="all") or []
        return [_row_to_insight_dict(r) for r in rows]

    def fetch_one(self, insight_id: str) -> Optional[Dict[str, Any]]:
        """Return full insight (including StructuredJson + MetricsJson) by ID."""
        row = execute_query(self._conn, """
            SELECT
                InsightID, Category, Title, Narrative,
                StructuredJson, MetricsJson,
                GeneratedAt, PeriodStart, PeriodEnd,
                ConfidenceScore, ModelVersion,
                PromptTokens, CompletionTokens
            FROM dbo.AIInsights
            WHERE InsightID = ?
        """, (insight_id,), fetch="one")
        if not row:
            return None
        return _row_to_insight_dict(row, include_json=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_insight_dict(r, include_json: bool = False) -> Dict[str, Any]:
    """Convert a pyodbc Row from AIInsights to a plain dict."""
    if include_json:
        # Full SELECT (13 columns)
        return {
            "insight_id":        str(r[0]).lower(),
            "category":          str(r[1]),
            "title":             str(r[2]),
            "narrative":         str(r[3]),
            "structured_json":   json.loads(r[4]) if r[4] else {},
            "metrics_json":      json.loads(r[5]) if r[5] else {},
            "generated_at":      r[6],
            "period_start":      r[7],
            "period_end":        r[8],
            "confidence_score":  float(r[9])  if r[9]  else None,
            "model_version":     str(r[10]) if r[10] else "gpt-4o",
            "prompt_tokens":     int(r[11]) if r[11] else None,
            "completion_tokens": int(r[12]) if r[12] else None,
        }
    # List SELECT (8 columns)
    return {
        "insight_id":       str(r[0]).lower(),
        "category":         str(r[1]),
        "title":            str(r[2]),
        "narrative":        str(r[3]),
        "generated_at":     r[4],
        "period_start":     r[5],
        "period_end":       r[6],
        "confidence_score": float(r[7]) if r[7] else None,
    }


def _compute_confidence(metrics: Dict, category: str) -> float:
    """
    Confidence score (0.0–1.0) = fraction of critical metric fields
    that are non-null and non-zero.

    This is computed from DATA COMPLETENESS, not from GPT-4o's self-assessment.
    A score of 1.0 means all expected data fields were populated.
    """
    if category == "Sales":
        critical = [
            metrics.get("total_revenue") or 0,
            metrics.get("total_orders") or 0,
            len(metrics.get("monthly_trend") or []),
            len(metrics.get("category_breakdown") or []),
            metrics.get("revenue_growth_pct"),  # may be None if no prior data
        ]
        # Revenue < $1 000 → minimal data; cap at 0.3
        if (metrics.get("total_revenue") or 0) < 1_000:
            return 0.3

    elif category == "Customers":
        critical = [
            metrics.get("total_customers") or 0,
            metrics.get("active_customers") or 0,
            len(metrics.get("segments") or []),
            metrics.get("new_customers_in_period") or 0,
        ]

    elif category == "Support":
        critical = [
            metrics.get("total_tickets") or 0,
            metrics.get("avg_csat"),
            metrics.get("sla24h_compliance_pct"),
            len(metrics.get("by_category") or []),
        ]
        if (metrics.get("total_tickets") or 0) == 0:
            return 0.2

    elif category == "Campaigns":
        critical = [
            metrics.get("total_campaigns") or 0,
            metrics.get("total_spend") or 0,
            len(metrics.get("by_type") or []),
        ]
        if (metrics.get("total_campaigns") or 0) == 0:
            return 0.2

    else:
        return 0.5

    non_null = sum(1 for v in critical if v is not None and v != 0)
    return round(min(non_null / max(len(critical), 1), 1.0), 3)


def _get_data_period(conn: pyodbc.Connection) -> Tuple[date, date]:
    """
    Query the actual date range of available sales data.
    Falls back to last 12 months if the table is empty.
    """
    row = execute_query(conn, """
        SELECT MIN(OrderDate), MAX(OrderDate)
        FROM dbo.vw_SalesSummary
        WHERE OrderStatus IN ('Completed', 'Shipped')
    """, fetch="one")
    if row and row[0] and row[1]:
        # pyodbc returns DATE columns as datetime.date
        start = row[0] if isinstance(row[0], date) else row[0].date()
        end   = row[1] if isinstance(row[1], date) else row[1].date()
        return start, end
    today = date.today()
    return today - timedelta(days=365), today


# ── Public entry point ────────────────────────────────────────────────────────

def run_insight_generation(
    conn: pyodbc.Connection,
    categories: List[str],
    period_start: Optional[date] = None,
    period_end:   Optional[date] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Orchestrate the full insight generation pipeline.

    Args:
        conn:          Open pyodbc connection (provided by FastAPI Depends).
        categories:    Which insight types to generate.
        period_start:  Start of analysis window (defaults to earliest data).
        period_end:    End of analysis window (defaults to latest data).
        force_refresh: If False, skip categories that already have an insight
                       for this exact period (idempotent re-runs).

    Returns:
        Dict with keys: status, generated_count, failed_categories,
        insight_ids, period_start, period_end,
        total_prompt_tokens, total_completion_tokens.
    """
    cfg = get_settings()

    if not cfg.azure_openai_endpoint or not cfg.azure_openai_key:
        raise RuntimeError(
            "Azure OpenAI credentials are not configured. "
            "Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY in .env."
        )

    # Resolve period (query actual data range if not supplied)
    if period_start is None or period_end is None:
        data_start, data_end = _get_data_period(conn)
        if period_start is None:
            period_start = data_start
        if period_end is None:
            period_end = data_end

    log.info(
        "Insight generation: categories=%s period=%s–%s force=%s",
        categories, period_start, period_end, force_refresh,
    )

    openai_client = AzureOpenAI(
        azure_endpoint=cfg.azure_openai_endpoint,
        api_key=cfg.azure_openai_key,
        api_version=_OPENAI_API_VERSION,
    )

    collector = MetricsCollector(conn)
    generator = InsightGenerator(openai_client, cfg.azure_openai_deployment)
    store     = InsightStore(conn)

    store.ensure_table()

    insight_ids:       List[str] = []
    failed_categories: List[str] = []
    total_pt = total_ct = 0

    for category in categories:
        # Skip if already generated for this period (unless force_refresh)
        if not force_refresh and store.insight_exists(category, period_start, period_end):
            log.info("Skipping %s — insight already exists for %s–%s", category, period_start, period_end)
            continue

        try:
            # 1 — Collect metrics
            log.info("Collecting %s metrics …", category)
            if category == "Sales":
                metrics = collector.collect_sales_metrics(period_start, period_end)
                structured, pt, ct = generator.generate_sales_insight(metrics)
            elif category == "Customers":
                metrics = collector.collect_customer_metrics(period_start, period_end)
                structured, pt, ct = generator.generate_churn_insight(metrics)
            elif category == "Support":
                metrics = collector.collect_support_metrics(period_start, period_end)
                structured, pt, ct = generator.generate_support_insight(metrics)
            elif category == "Campaigns":
                metrics = collector.collect_campaign_metrics(period_start, period_end)
                structured, pt, ct = generator.generate_campaign_insight(metrics)
            else:
                log.warning("Unknown category '%s' — skipping.", category)
                continue

            total_pt += pt
            total_ct += ct

            # 2 — Confidence score (data completeness)
            confidence = _compute_confidence(metrics, category)

            # 3 — Persist
            title     = str(structured.get("title", f"{category} Insight — {period_start}"))
            narrative = str(structured.get("narrative", ""))

            insight_id = store.save(
                category=category,
                title=title,
                narrative=narrative,
                structured=structured,
                metrics=metrics,
                period_start=period_start,
                period_end=period_end,
                confidence=confidence,
                model_version=cfg.azure_openai_deployment,
                prompt_tokens=pt,
                completion_tokens=ct,
            )
            insight_ids.append(insight_id)
            log.info(
                "Saved %s insight %s  confidence=%.3f  tokens=%d+%d",
                category, insight_id, confidence, pt, ct,
            )

        except (APIError, RateLimitError) as exc:
            log.error("OpenAI error for %s insight: %s", category, exc)
            failed_categories.append(category)

        except Exception as exc:
            # Partial results are better than aborting everything
            log.error("Failed to generate %s insight: %s", category, exc, exc_info=True)
            failed_categories.append(category)

    status = (
        "completed" if not failed_categories
        else ("partial" if insight_ids else "failed")
    )

    return {
        "status":                  status,
        "generated_count":         len(insight_ids),
        "failed_categories":       failed_categories,
        "insight_ids":             insight_ids,
        "period_start":            period_start,
        "period_end":              period_end,
        "total_prompt_tokens":     total_pt,
        "total_completion_tokens": total_ct,
    }
