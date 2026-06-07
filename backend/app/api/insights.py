"""
backend/app/api/insights.py

AI Insights API — GPT-4o generated business narratives stored in Azure SQL.

Endpoints:
  GET  /api/insights                  → paginated list of latest insights
  GET  /api/insights/{insight_id}     → full insight with structured JSON
  POST /api/insights/generate         → trigger generation (Admin only)

Role requirements:
  GET  endpoints — Viewer and above
  POST /generate — Admin only (generation consumes OpenAI tokens)

Generation note:
  POST /generate runs synchronously. Each category requires one GPT-4o call
  (~5–15 s), so generating all 4 categories may take 20–60 s. This is
  intentional: the endpoint is admin-only and called infrequently.
  The response includes created insight IDs so callers can fetch them
  immediately without polling.
"""

import logging
from typing import List, Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.api.deps import get_db_conn, require_role
from app.core.appinsights import track_event
from app.models.schemas import (
    GenerateInsightRequest,
    GenerateInsightResponse,
    InsightDetail,
    InsightRow,
    UserInfo,
)
from app.services.insights_service import InsightStore, run_insight_generation

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/insights", tags=["AI Insights"])

_viewer = require_role("Viewer")
_admin  = require_role("Admin")

_ALLOWED_CATEGORIES = {"Sales", "Customers", "Support", "Campaigns"}


# ── GET /api/insights ─────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=List[InsightRow],
    summary="List latest AI-generated business insights",
    description=(
        "Returns the most recent AI-generated insights from dbo.AIInsights, "
        "ordered by generation time descending. Optionally filter by category. "
        "Returns an empty list if the AIInsights table does not yet exist."
    ),
)
def get_insights(
    limit: int = Query(20, ge=1, le=100, description="Maximum insights to return"),
    category: Optional[str] = Query(
        None,
        description="Filter by category: Sales | Customers | Support | Campaigns",
    ),
    conn: pyodbc.Connection = Depends(get_db_conn),
    _user: UserInfo = Depends(_viewer),
) -> List[InsightRow]:
    if category and category not in _ALLOWED_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"category must be one of: {sorted(_ALLOWED_CATEGORIES)}",
        )

    # Table is created on first generation run — gracefully return empty list before that
    try:
        store = InsightStore(conn)
        rows  = store.fetch_list(limit=limit, category=category)
    except Exception as exc:
        if "Invalid object name" in str(exc) or "AIInsights" in str(exc):
            log.info("AIInsights table not yet created — returning empty list.")
            return []
        log.error("Error fetching insights: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve insights.",
        ) from exc

    return [
        InsightRow(
            insight_id=r["insight_id"],
            category=r["category"],
            title=r["title"],
            narrative=r["narrative"],
            generated_at=r["generated_at"],
            period_start=r["period_start"],
            period_end=r["period_end"],
            confidence_score=r["confidence_score"],
        )
        for r in rows
    ]


# ── GET /api/insights/{insight_id} ────────────────────────────────────────────

@router.get(
    "/{insight_id}",
    response_model=InsightDetail,
    summary="Get full insight detail including structured JSON",
    description=(
        "Returns the complete insight record: headline fields, GPT-4o structured "
        "output (key_findings, recommendations, risk_flags, …), and the raw metrics "
        "used as prompt context. Useful for debugging or deep-dive analysis."
    ),
)
def get_insight_detail(
    insight_id: str = Path(
        ...,
        description="Insight UUID (from GET /api/insights or POST /api/insights/generate)",
        min_length=36,
        max_length=36,
    ),
    conn: pyodbc.Connection = Depends(get_db_conn),
    _user: UserInfo = Depends(_viewer),
) -> InsightDetail:
    try:
        store = InsightStore(conn)
        row   = store.fetch_one(insight_id)
    except Exception as exc:
        log.error("Error fetching insight %s: %s", insight_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve insight.",
        ) from exc

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Insight '{insight_id}' not found.",
        )

    return InsightDetail(
        insight_id=row["insight_id"],
        category=row["category"],
        title=row["title"],
        narrative=row["narrative"],
        generated_at=row["generated_at"],
        period_start=row["period_start"],
        period_end=row["period_end"],
        confidence_score=row["confidence_score"],
        structured_json=row["structured_json"],
        metrics_json=row["metrics_json"],
        model_version=row["model_version"],
        prompt_tokens=row["prompt_tokens"],
        completion_tokens=row["completion_tokens"],
    )


# ── POST /api/insights/generate ───────────────────────────────────────────────

@router.post(
    "/generate",
    response_model=GenerateInsightResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate AI insights (Admin only)",
    description=(
        "Runs the GPT-4o insight generation pipeline for the requested categories. "
        "Each category: (1) queries Azure SQL views for business metrics, "
        "(2) calls GPT-4o with a category-specific prompt to produce structured JSON "
        "plus a human-readable narrative, (3) stores the result in dbo.AIInsights. "
        "If force_refresh=False (default), skips categories that already have an "
        "insight for the exact period. "
        "Period defaults to the full date range of available sales data if omitted. "
        "Latency: ~5–15 s per category; 20–60 s total for all four."
    ),
)
def generate_insights(
    body: GenerateInsightRequest,
    conn: pyodbc.Connection = Depends(get_db_conn),
    user: UserInfo = Depends(_admin),
) -> GenerateInsightResponse:
    log.info(
        "Insight generation requested by %s: categories=%s period=%s–%s force=%s",
        user.username, body.categories,
        body.period_start, body.period_end,
        body.force_refresh,
    )

    try:
        result = run_insight_generation(
            conn=conn,
            categories=body.categories,
            period_start=body.period_start,
            period_end=body.period_end,
            force_refresh=body.force_refresh,
        )
    except RuntimeError as exc:
        # Missing Azure OpenAI credentials
        log.warning("Insight generation configuration error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log.error("Insight generation failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Insight generation failed. Check server logs for details.",
        ) from exc

    track_event(
        "InsightGenerationCompleted",
        {
            "triggered_by":      user.username,
            "status":            result["status"],
            "generated_count":   result["generated_count"],
            "failed_categories": ",".join(result["failed_categories"]),
            "total_tokens":      result["total_prompt_tokens"] + result["total_completion_tokens"],
        },
    )

    return GenerateInsightResponse(
        status=result["status"],
        generated_count=result["generated_count"],
        failed_categories=result["failed_categories"],
        insight_ids=result["insight_ids"],
        period_start=result["period_start"],
        period_end=result["period_end"],
        total_prompt_tokens=result["total_prompt_tokens"],
        total_completion_tokens=result["total_completion_tokens"],
    )
