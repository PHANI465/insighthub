"""
backend/app/services/metrics_service.py

Queries the Azure SQL reporting views to produce KPI data for the
InsightHub frontend and Power BI dashboards.

All SQL in this file uses parameterised ? placeholders.
Column names in SQL are hardcoded constants — never constructed from
user input — so there is no SQL injection risk.
"""

import logging
from datetime import date
from typing import List, Optional

import pyodbc

from app.core.database import execute_query, rows_to_dicts
from app.models.schemas import (
    CampaignROIRow,
    CustomerSegmentStat,
    KPISummary,
    ProductPerformanceRow,
    RevenueTrend,
    SupportMetricsRow,
)

log = logging.getLogger(__name__)


# ── Helper ────────────────────────────────────────────────────────────────────

def _date_filter(from_date: Optional[date], to_date: Optional[date]) -> tuple[str, tuple]:
    """Build a WHERE clause fragment and params tuple for date range filtering.
    Always returns at least WHERE 1=1 so callers can safely append AND clauses.
    """
    conditions = ["1=1"]
    params = []
    if from_date:
        conditions.append("OrderDate >= ?")
        params.append(str(from_date))
    if to_date:
        conditions.append("OrderDate <= ?")
        params.append(str(to_date))
    return "WHERE " + " AND ".join(conditions), tuple(params)


# ── KPI Summary ───────────────────────────────────────────────────────────────

def get_kpi_summary(
    conn: pyodbc.Connection,
    from_date: Optional[date] = None,
    to_date:   Optional[date] = None,
) -> KPISummary:
    """
    Aggregate headline KPIs across all completed/shipped orders.
    Used for the executive dashboard cards.
    """
    where, params = _date_filter(from_date, to_date)
    sql_sales = f"""
        SELECT
            COALESCE(SUM(GrossRevenue), 0)              AS TotalRevenue,
            COUNT(DISTINCT OrderID)                     AS TotalOrders,
            COUNT(DISTINCT CustomerKey)                 AS UniqueCustomers,
            COALESCE(AVG(GrossRevenue), 0)              AS AvgOrderValue,
            COALESCE(SUM(GrossProfit), 0)               AS GrossProfit,
            CASE WHEN SUM(GrossRevenue) > 0
                 THEN SUM(GrossProfit) / SUM(GrossRevenue) * 100
                 ELSE 0 END                             AS GrossMarginPct
        FROM dbo.vw_SalesSummary
        {where}
        AND OrderStatus IN ('Completed', 'Shipped')
    """
    sales_row = execute_query(conn, sql_sales, params or None, fetch="one")

    sql_support = """
        SELECT
            COUNT(*)                               AS TotalTickets,
            SUM(CASE WHEN TicketStatus = 'Open'
                      OR TicketStatus = 'In Progress' THEN 1 ELSE 0 END) AS OpenTickets,
            AVG(CAST(SatisfactionRating AS FLOAT)) AS AvgCSAT
        FROM dbo.FactSupportTickets
    """
    sup_row = execute_query(conn, sql_support, fetch="one")

    sql_campaigns = """
        SELECT
            COUNT(*)      AS TotalCampaigns,
            MAX(ROI_Pct)  AS TopROI
        FROM dbo.vw_CampaignROI
    """
    camp_row = execute_query(conn, sql_campaigns, fetch="one")

    sql_total_customers = "SELECT COUNT(*) FROM dbo.DimCustomer WHERE AccountStatus = 'Active'"
    total_customers = execute_query(conn, sql_total_customers, fetch="one")[0]

    return KPISummary(
        total_revenue=round(float(sales_row[0] or 0), 2),
        total_orders=int(sales_row[1] or 0),
        total_customers=int(total_customers or 0),
        avg_order_value=round(float(sales_row[3] or 0), 2),
        gross_profit=round(float(sales_row[4] or 0), 2),
        gross_margin_pct=round(float(sales_row[5] or 0), 2),
        total_tickets=int(sup_row[0] or 0),
        avg_csat=round(float(sup_row[2]), 2) if sup_row[2] else None,
        open_tickets=int(sup_row[1] or 0),
        total_campaigns=int(camp_row[0] or 0),
        top_campaign_roi_pct=round(float(camp_row[1] or 0), 2),
        period_label="All time" if not from_date else f"{from_date} – {to_date or 'today'}",
    )


# ── Revenue trend ─────────────────────────────────────────────────────────────

def get_revenue_trend(
    conn: pyodbc.Connection,
    granularity: str = "month",
    from_date: Optional[date] = None,
    to_date:   Optional[date] = None,
) -> List[RevenueTrend]:
    """
    Revenue and profit aggregated by time period.
    Granularity: 'day', 'week', 'month', 'quarter', 'year'.
    """
    # period_label based on granularity
    period_expr = {
        "day":     "CONVERT(VARCHAR(10), OrderDate, 120)",
        "week":    "CAST(CalendarYear AS VARCHAR) + '-W' + RIGHT('0' + CAST(WeekOfYear AS VARCHAR), 2)",
        "month":   "MonthYear",
        "quarter": "CAST(CalendarYear AS VARCHAR) + ' ' + QuarterLabel",
        "year":    "CAST(CalendarYear AS VARCHAR)",
    }.get(granularity, "MonthYear")

    where_parts = ["OrderStatus IN ('Completed', 'Shipped')"]
    params = []
    if from_date:
        where_parts.append("OrderDate >= ?")
        params.append(str(from_date))
    if to_date:
        where_parts.append("OrderDate <= ?")
        params.append(str(to_date))

    where_clause = "WHERE " + " AND ".join(where_parts)
    sql = f"""
        SELECT
            {period_expr}           AS Period,
            SUM(GrossRevenue)       AS Revenue,
            SUM(GrossProfit)        AS GrossProfit,
            COUNT(DISTINCT OrderID) AS OrderCount,
            AVG(GrossRevenue)       AS AvgOrderValue
        FROM dbo.vw_SalesSummary
        {where_clause}
        GROUP BY {period_expr}
        ORDER BY MIN(OrderDate)
    """
    rows = execute_query(conn, sql, tuple(params) if params else None, fetch="all")
    return [
        RevenueTrend(
            period=str(r[0]),
            revenue=round(float(r[1] or 0), 2),
            gross_profit=round(float(r[2] or 0), 2),
            order_count=int(r[3] or 0),
            avg_order_value=round(float(r[4] or 0), 2),
        )
        for r in (rows or [])
    ]


# ── Customer analytics ────────────────────────────────────────────────────────

def get_customer_segments(conn: pyodbc.Connection) -> List[CustomerSegmentStat]:
    """Revenue and count by customer segment."""
    sql = """
        SELECT
            dc.CustomerSegment,
            COUNT(DISTINCT dc.CustomerKey)           AS CustomerCount,
            COALESCE(SUM(fs.GrossRevenue), 0)        AS TotalRevenue,
            AVG(dc.LifetimeValue)                    AS AvgLTV,
            COALESCE(AVG(fs.GrossRevenue), 0)        AS AvgOrderValue,
            SUM(CASE WHEN dc.AccountStatus = 'Inactive' THEN 1 ELSE 0 END) AS ChurnRisk
        FROM dbo.DimCustomer dc
        LEFT JOIN dbo.FactSales fs
            ON dc.CustomerKey = fs.CustomerKey
            AND fs.OrderStatus NOT IN ('Cancelled')
        GROUP BY dc.CustomerSegment
        ORDER BY TotalRevenue DESC
    """
    rows = execute_query(conn, sql, fetch="all") or []
    return [
        CustomerSegmentStat(
            segment=str(r[0]),
            customer_count=int(r[1]),
            total_revenue=round(float(r[2] or 0), 2),
            avg_ltv=round(float(r[3] or 0), 2),
            avg_order_value=round(float(r[4] or 0), 2),
            churn_risk_count=int(r[5] or 0),
        )
        for r in rows
    ]


# ── Product performance ───────────────────────────────────────────────────────

def get_product_performance(
    conn: pyodbc.Connection,
    category: Optional[str] = None,
    limit: int = 50,
) -> List[ProductPerformanceRow]:
    """Top products by revenue, optionally filtered by category."""
    where = "WHERE 1=1"
    params = []
    if category:
        where += " AND Category = ?"
        params.append(category)

    sql = f"""
        SELECT TOP (?)
            ProductID, ProductName, Category, Brand,
            TotalUnitsSold, TotalRevenue, TotalGrossProfit,
            CurrentMarginPct, AvgDiscountPct, CustomerRating,
            CurrentStockQty, NeedsReorder
        FROM dbo.vw_ProductPerformance
        {where}
        ORDER BY TotalRevenue DESC
    """
    params.insert(0, limit)
    rows = execute_query(conn, sql, tuple(params), fetch="all") or []
    return [
        ProductPerformanceRow(
            product_id=str(r[0]),
            product_name=str(r[1]),
            category=str(r[2]),
            brand=str(r[3]),
            units_sold=int(r[4] or 0),
            total_revenue=round(float(r[5] or 0), 2),
            gross_profit=round(float(r[6] or 0), 2),
            margin_pct=round(float(r[7] or 0), 2),
            avg_discount_pct=round(float(r[8] or 0), 2),
            rating=round(float(r[9]), 1) if r[9] else None,
            stock_qty=int(r[10] or 0),
            needs_reorder=bool(r[11]),
        )
        for r in rows
    ]


# ── Support metrics ───────────────────────────────────────────────────────────

def get_support_metrics(
    conn: pyodbc.Connection,
    from_date: Optional[date] = None,
    to_date:   Optional[date] = None,
) -> List[SupportMetricsRow]:
    """Support ticket KPIs grouped by month, category, and priority."""
    where_parts = ["1=1"]
    params = []
    if from_date:
        where_parts.append("CreatedDate >= ?")
        params.append(str(from_date))
    if to_date:
        where_parts.append("CreatedDate <= ?")
        params.append(str(to_date))

    sql = f"""
        SELECT
            CreatedMonthYear, Category, Priority,
            TotalTickets, ResolvedTickets, EscalatedTickets,
            AvgResolutionHours, AvgCSAT, SLA24h_CompliancePct
        FROM dbo.vw_SupportMetrics
        WHERE {' AND '.join(where_parts)}
        ORDER BY CreatedDate DESC
    """
    rows = execute_query(conn, sql, tuple(params) if params else None, fetch="all") or []
    return [
        SupportMetricsRow(
            period=str(r[0]),
            category=str(r[1]),
            priority=str(r[2]),
            total_tickets=int(r[3] or 0),
            resolved_tickets=int(r[4] or 0),
            escalated_tickets=int(r[5] or 0),
            avg_resolution_hours=round(float(r[6]), 1) if r[6] else None,
            avg_csat=round(float(r[7]), 2) if r[7] else None,
            sla_compliance_pct=round(float(r[8]), 2) if r[8] else None,
        )
        for r in rows
    ]


# ── Campaign ROI ──────────────────────────────────────────────────────────────

def get_campaign_roi(
    conn: pyodbc.Connection,
    limit: int = 20,
) -> List[CampaignROIRow]:
    """Campaign performance summary ordered by ROI descending."""
    sql = """
        SELECT TOP (?)
            CampaignName, CampaignType, Region,
            Budget, ActualSpend, RevenueGenerated, ROI_Pct,
            Impressions, Clicks, Conversions, CTR_Pct,
            ConversionRate_Pct, ROI_Band
        FROM dbo.vw_CampaignROI
        ORDER BY ROI_Pct DESC
    """
    rows = execute_query(conn, sql, (limit,), fetch="all") or []
    return [
        CampaignROIRow(
            campaign_name=str(r[0]),
            campaign_type=str(r[1]),
            region=str(r[2]),
            budget=round(float(r[3] or 0), 2),
            spend=round(float(r[4] or 0), 2),
            revenue=round(float(r[5] or 0), 2),
            roi_pct=round(float(r[6] or 0), 2),
            impressions=int(r[7] or 0),
            clicks=int(r[8] or 0),
            conversions=int(r[9] or 0),
            ctr_pct=round(float(r[10] or 0), 3),
            conversion_rate_pct=round(float(r[11] or 0), 3),
            roi_band=str(r[12]),
        )
        for r in rows
    ]
