"""
backend/app/api/metrics.py

Metrics routes — KPI data from Azure SQL reporting views.

  GET  /api/metrics/dashboard    → executive KPI summary cards
  GET  /api/metrics/revenue      → revenue trend over time
  GET  /api/metrics/customers    → customer segment breakdown
  GET  /api/metrics/products     → product performance table
  GET  /api/metrics/support      → support ticket KPIs
  GET  /api/metrics/campaigns    → campaign ROI summary

All endpoints require at minimum the 'Viewer' role.
"""

from datetime import date
from typing import List, Optional

import pyodbc
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_db_conn, require_role
from app.models.schemas import (
    CampaignROIRow,
    CustomerSegmentStat,
    KPISummary,
    ProductPerformanceRow,
    RevenueTrend,
    SupportMetricsRow,
    UserInfo,
)
from app.services import metrics_service

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])

_viewer = require_role("Viewer")
_analyst = require_role("Analyst")


@router.get(
    "/dashboard",
    response_model=KPISummary,
    summary="Executive KPI dashboard summary",
)
def get_dashboard(
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date:   Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    conn: pyodbc.Connection = Depends(get_db_conn),
    _user: UserInfo = Depends(_viewer),
) -> KPISummary:
    """Aggregate KPI cards: total revenue, orders, customers, CSAT, campaigns."""
    return metrics_service.get_kpi_summary(conn, from_date, to_date)


@router.get(
    "/revenue",
    response_model=List[RevenueTrend],
    summary="Revenue trend over time",
)
def get_revenue_trend(
    granularity: str = Query("month", description="day | week | month | quarter | year"),
    from_date: Optional[date] = Query(None),
    to_date:   Optional[date] = Query(None),
    conn: pyodbc.Connection = Depends(get_db_conn),
    _user: UserInfo = Depends(_viewer),   # Viewer+ — shown on Executive Dashboard
) -> List[RevenueTrend]:
    """Revenue, gross profit, and order count grouped by the requested time granularity."""
    return metrics_service.get_revenue_trend(conn, granularity, from_date, to_date)


@router.get(
    "/customers",
    response_model=List[CustomerSegmentStat],
    summary="Customer segment breakdown",
)
def get_customer_segments(
    conn: pyodbc.Connection = Depends(get_db_conn),
    _user: UserInfo = Depends(_analyst),
) -> List[CustomerSegmentStat]:
    """Revenue, LTV, and churn risk by customer segment (Bronze/Silver/Gold/Platinum)."""
    return metrics_service.get_customer_segments(conn)


@router.get(
    "/products",
    response_model=List[ProductPerformanceRow],
    summary="Product performance table",
)
def get_product_performance(
    category: Optional[str] = Query(None, description="Filter by product category"),
    limit: int = Query(50, ge=1, le=200, description="Max rows to return"),
    conn: pyodbc.Connection = Depends(get_db_conn),
    _user: UserInfo = Depends(_analyst),
) -> List[ProductPerformanceRow]:
    """Top products by revenue with units sold, margin %, and reorder alerts."""
    return metrics_service.get_product_performance(conn, category, limit)


@router.get(
    "/support",
    response_model=List[SupportMetricsRow],
    summary="Support ticket KPIs",
)
def get_support_metrics(
    from_date: Optional[date] = Query(None),
    to_date:   Optional[date] = Query(None),
    conn: pyodbc.Connection = Depends(get_db_conn),
    _user: UserInfo = Depends(_analyst),
) -> List[SupportMetricsRow]:
    """Ticket resolution rates, CSAT scores, and SLA compliance by category and priority."""
    return metrics_service.get_support_metrics(conn, from_date, to_date)


@router.get(
    "/campaigns",
    response_model=List[CampaignROIRow],
    summary="Campaign ROI summary",
)
def get_campaign_roi(
    limit: int = Query(20, ge=1, le=100),
    conn: pyodbc.Connection = Depends(get_db_conn),
    _user: UserInfo = Depends(_viewer),   # Viewer+ — shown on Executive Dashboard
) -> List[CampaignROIRow]:
    """Marketing campaign ROI, CTR, conversion rate ordered by ROI descending."""
    return metrics_service.get_campaign_roi(conn, limit)
