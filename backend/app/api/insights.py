"""
backend/app/api/insights.py

AI Insights routes — GPT-4o generated business narratives stored in Azure SQL.

  GET  /api/insights              → retrieve latest stored insights
  POST /api/insights/generate     → trigger insight generation (Admin only)

The full insight generation engine is built in Phase 7 (insights-engine/).
This module defines the API surface and response contract.
"""

import logging
from typing import List, Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_db_conn, get_current_user, require_role
from app.core.appinsights import track_event
from app.core.database import execute_query
from app.models.schemas import GenerateInsightRequest, InsightRow, UserInfo

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/insights", tags=["AI Insights"])

_viewer  = require_role("Viewer")
_analyst = require_role("Analyst")
_admin   = require_role("Admin")

# ── SQL queries ───────────────────────────────────────────────────────────────

_SELECT_INSIGHTS = """
SELECT TOP (?)
    InsightID, Category, Title, Narrative,
    GeneratedAt, PeriodStart, PeriodEnd, ConfidenceScore
FROM dbo.AIInsights
WHERE 1=1
{category_filter}
ORDER BY GeneratedAt DESC
"""

_CHECK_INSIGHTS_TABLE = """
SELECT COUNT(*) FROM sys.tables WHERE name = 'AIInsights' AND schema_id = SCHEMA_ID('dbo')
"""


@router.get(
    "",
    response_model=List[InsightRow],
    summary="Get latest AI-generated business insights",
)
def get_insights(
    limit: int = Query(10, ge=1, le=50, description="Number of insights to return"),
    category: Optional[str] = Query(None, description="Filter: Sales | Customers | Support | Campaigns"),
    conn: pyodbc.Connection = Depends(get_db_conn),
    _user: UserInfo = Depends(_viewer),
) -> List[InsightRow]:
    """
    Returns the most recent AI-generated business insights stored in Azure SQL.
    The AIInsights table is populated by the insights-engine (Phase 7).
    Until Phase 7 runs, returns an empty list.
    """
    # Check if the AIInsights table exists (created in Phase 7 migration)
    table_exists = execute_query(conn, _CHECK_INSIGHTS_TABLE, fetch="one")
    if not table_exists or table_exists[0] == 0:
        # Table not yet created — return empty list (Phase 7 creates it)
        log.info("AIInsights table not yet created. Returning empty insights list.")
        return []

    category_filter = ""
    params = [limit]
    if category:
        allowed = {"Sales", "Customers", "Support", "Campaigns", "Products"}
        if category not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"category must be one of: {allowed}",
            )
        category_filter = "AND Category = ?"
        params.append(category)

    sql = _SELECT_INSIGHTS.format(category_filter=category_filter)
    rows = execute_query(conn, sql, tuple(params), fetch="all") or []

    return [
        InsightRow(
            insight_id=r[0],
            category=r[1],
            title=r[2],
            narrative=r[3],
            generated_at=r[4],
            period_start=r[5],
            period_end=r[6],
            confidence_score=float(r[7]) if r[7] else None,
        )
        for r in rows
    ]


@router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger AI insight generation (Admin only)",
    description=(
        "Starts an asynchronous insight generation job. "
        "GPT-4o will analyse the latest metrics and write narratives to AIInsights. "
        "Full implementation in Phase 7 (insights-engine/)."
    ),
)
def generate_insights(
    body: GenerateInsightRequest,
    _user: UserInfo = Depends(_admin),
) -> dict:
    """
    Admin-only endpoint to trigger insight regeneration.
    Returns 202 Accepted — the generation runs asynchronously.
    Phase 7 will connect this to the insights-engine.
    """
    track_event(
        "InsightGenerationTriggered",
        {
            "categories": ",".join(body.categories),
            "force_refresh": body.force_refresh,
            "triggered_by": _user.username,
        },
    )
    log.info(
        "Insight generation triggered by %s for categories: %s",
        _user.username, body.categories,
    )
    return {
        "status": "accepted",
        "message": (
            f"Insight generation queued for: {', '.join(body.categories)}. "
            "Full pipeline implemented in Phase 7."
        ),
        "categories": body.categories,
    }
