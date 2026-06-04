-- =============================================================================
-- InsightHub — Reporting Views
-- File        : 05_views.sql
-- Database    : Azure SQL  (insighthub-db)
-- Run order   : 5 of 6  (run AFTER all tables and indexes)
-- Description : Creates five reporting views that pre-join facts with
--               dimensions.  Power BI datasets, the FastAPI backend, and the
--               AI Insights Engine query these views — never raw fact tables.
--
-- Design principles
-- ─────────────────
-- • Views are thin wrappers (SELECT only) — no business logic beyond joins.
-- • Column aliases use PascalCase to match Power BI field naming conventions.
-- • Every view is created with CREATE OR ALTER (idempotent re-deployments).
-- • No ORDER BY inside views — ordering is the responsibility of the caller.
-- =============================================================================

SET NOCOUNT ON;
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. vw_SalesSummary
-- ─────────────────────────────────────────────────────────────────────────────
GO
CREATE OR ALTER VIEW dbo.vw_SalesSummary AS
SELECT
    -- Date grain
    dd.FullDate                         AS OrderDate,
    dd.DateKey                          AS OrderDateKey,
    dd.[Year]                           AS CalendarYear,
    dd.Quarter                          AS CalendarQuarter,
    dd.QuarterLabel                     AS QuarterLabel,
    dd.MonthNumber                      AS MonthNumber,
    dd.MonthName                        AS MonthName,
    dd.MonthYearLabel                   AS MonthYear,
    dd.FiscalYear                       AS FiscalYear,
    dd.FiscalQuarter                    AS FiscalQuarter,
    dd.IsWeekend                        AS IsWeekend,
    dd.IsUSHoliday                      AS IsHoliday,

    -- Customer grain
    dc.CustomerKey                      AS CustomerKey,
    dc.CustomerSegment                  AS CustomerSegment,
    dc.AgeGroup                         AS CustomerAgeGroup,
    dc.PreferredChannel                 AS CustomerPreferredChannel,

    -- Product grain
    dp.Category                         AS ProductCategory,
    dp.Subcategory                      AS ProductSubcategory,
    dp.Brand                            AS Brand,
    dp.ProductStatus                    AS ProductStatus,

    -- Geography grain
    dg.Country                          AS ShippingCountry,
    dg.StateCode                        AS ShippingState,
    dg.WorldRegion                      AS WorldRegion,
    dg.IsUSA                            AS IsUSOrder,

    -- Order attributes
    fs.OrderStatus                      AS OrderStatus,
    fs.PaymentMethod                    AS PaymentMethod,
    fs.OrderChannel                     AS OrderChannel,

    -- Additive revenue measures
    fs.Quantity                         AS Quantity,
    fs.UnitPrice                        AS UnitPrice,
    fs.DiscountAmount                   AS DiscountAmount,
    fs.DiscountPct                      AS DiscountPct,
    fs.LineTotal                        AS LineTotal,
    fs.ShippingAmount                   AS ShippingAmount,
    fs.TaxAmount                        AS TaxAmount,
    fs.GrossRevenue                     AS GrossRevenue,
    fs.CostOfGoods                      AS CostOfGoods,
    fs.GrossProfit                      AS GrossProfit,

    -- Degenerate dimensions (for drill-through)
    fs.OrderID                          AS OrderID,
    fs.LineItemID                       AS LineItemID
FROM
    dbo.FactSales            fs
    INNER JOIN dbo.DimDate       dd ON fs.OrderDateKey   = dd.DateKey
    INNER JOIN dbo.DimCustomer   dc ON fs.CustomerKey    = dc.CustomerKey
    INNER JOIN dbo.DimProduct    dp ON fs.ProductKey     = dp.ProductKey
    INNER JOIN dbo.DimGeography  dg ON fs.GeographyKey   = dg.GeographyKey;
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. vw_CustomerAnalytics
--    FIX: Joins directly to FactSales + DimDate instead of vw_SalesSummary
--    to avoid the "Invalid column name CustomerKey" error.
-- ─────────────────────────────────────────────────────────────────────────────
GO
CREATE OR ALTER VIEW dbo.vw_CustomerAnalytics AS
SELECT
    dc.CustomerKey                      AS CustomerKey,
    dc.CustomerID                       AS CustomerID,
    dc.FullName                         AS CustomerName,
    dc.Email                            AS Email,
    dc.CustomerSegment                  AS Segment,
    dc.AccountStatus                    AS AccountStatus,
    dc.AgeGroup                         AS AgeGroup,
    dc.RegistrationDate                 AS RegistrationDate,
    dc.LifetimeValue                    AS StoredLifetimeValue,
    dc.MarketingOptIn                   AS MarketingOptIn,
    dc.PreferredChannel                 AS PreferredChannel,
    dc.ReferralSource                   AS ReferralSource,

    -- Aggregated order metrics
    COUNT(DISTINCT fs.OrderID)          AS TotalOrders,
    SUM(fs.Quantity)                    AS TotalItemsPurchased,
    SUM(fs.GrossRevenue)                AS CalculatedLTV,
    SUM(fs.GrossProfit)                 AS TotalProfit,
    AVG(fs.GrossRevenue)                AS AvgOrderValue,
    MAX(dd.FullDate)                    AS LastOrderDate,
    MIN(dd.FullDate)                    AS FirstOrderDate,
    SUM(fs.DiscountAmount)              AS TotalDiscountsReceived,

    -- Support metrics
    COUNT(DISTINCT fst.TicketID)        AS TotalSupportTickets,
    AVG(CAST(fst.SatisfactionRating AS DECIMAL(5,2))) AS AvgSatisfactionRating,
    SUM(CASE WHEN fst.IsEscalated = 1 THEN 1 ELSE 0 END) AS EscalatedTickets
FROM
    dbo.DimCustomer dc
    LEFT JOIN dbo.FactSales fs
        ON dc.CustomerKey = fs.CustomerKey
        AND fs.OrderStatus NOT IN ('Cancelled')
    LEFT JOIN dbo.DimDate dd
        ON fs.OrderDateKey = dd.DateKey
    LEFT JOIN dbo.FactSupportTickets fst
        ON dc.CustomerKey = fst.CustomerKey
GROUP BY
    dc.CustomerKey, dc.CustomerID, dc.FullName, dc.Email,
    dc.CustomerSegment, dc.AccountStatus, dc.AgeGroup, dc.RegistrationDate,
    dc.LifetimeValue, dc.MarketingOptIn, dc.PreferredChannel, dc.ReferralSource;
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. vw_ProductPerformance
-- ─────────────────────────────────────────────────────────────────────────────
GO
CREATE OR ALTER VIEW dbo.vw_ProductPerformance AS
SELECT
    dp.ProductKey                               AS ProductKey,
    dp.ProductID                                AS ProductID,
    dp.ProductName                              AS ProductName,
    dp.SKU                                      AS SKU,
    dp.Brand                                    AS Brand,
    dp.Category                                 AS Category,
    dp.Subcategory                              AS Subcategory,
    dp.UnitPrice                                AS CurrentUnitPrice,
    dp.CostPrice                                AS CurrentCostPrice,
    dp.MarginPct                                AS CurrentMarginPct,
    dp.ProductStatus                            AS ProductStatus,
    dp.Rating                                   AS CustomerRating,
    dp.ReviewCount                              AS ReviewCount,
    dp.StockQuantity                            AS CurrentStockQty,
    dp.ReorderLevel                             AS ReorderLevel,
    CASE WHEN dp.StockQuantity <= dp.ReorderLevel
         THEN 1 ELSE 0 END                      AS NeedsReorder,

    -- Sales aggregates
    COALESCE(SUM(fs.Quantity), 0)               AS TotalUnitsSold,
    COALESCE(SUM(fs.LineTotal), 0)              AS TotalRevenue,
    COALESCE(SUM(fs.GrossProfit), 0)            AS TotalGrossProfit,
    COALESCE(SUM(fs.DiscountAmount), 0)         AS TotalDiscountGiven,
    COALESCE(COUNT(DISTINCT fs.OrderID), 0)     AS OrderCount,
    COALESCE(AVG(fs.DiscountPct), 0)            AS AvgDiscountPct
FROM
    dbo.DimProduct dp
    LEFT JOIN dbo.FactSales fs
        ON dp.ProductKey = fs.ProductKey
        AND fs.OrderStatus NOT IN ('Cancelled')
GROUP BY
    dp.ProductKey, dp.ProductID, dp.ProductName, dp.SKU, dp.Brand,
    dp.Category, dp.Subcategory, dp.UnitPrice, dp.CostPrice, dp.MarginPct,
    dp.ProductStatus, dp.Rating, dp.ReviewCount, dp.StockQuantity, dp.ReorderLevel;
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. vw_SupportMetrics
-- ─────────────────────────────────────────────────────────────────────────────
GO
CREATE OR ALTER VIEW dbo.vw_SupportMetrics AS
SELECT
    -- Date grain
    cd.FullDate                                     AS CreatedDate,
    cd.[Year]                                       AS CreatedYear,
    cd.QuarterLabel                                 AS CreatedQuarter,
    cd.MonthYearLabel                               AS CreatedMonthYear,

    -- Employee grain
    de.FullName                                     AS AssignedAgent,
    de.Department                                   AS Department,
    de.OfficeLocation                               AS OfficeLocation,

    -- Ticket attributes
    fst.Category                                    AS Category,
    fst.Priority                                    AS Priority,
    fst.TicketStatus                                AS TicketStatus,
    fst.InboundChannel                              AS InboundChannel,

    -- Counts
    COUNT(fst.TicketKey)                            AS TotalTickets,
    SUM(CAST(fst.IsResolved AS INT))                AS ResolvedTickets,
    SUM(CAST(fst.IsEscalated AS INT))               AS EscalatedTickets,

    -- Time metrics
    AVG(fst.ResolutionHours)                        AS AvgResolutionHours,
    AVG(fst.FirstResponseHours)                     AS AvgFirstResponseHours,
    MIN(fst.ResolutionHours)                        AS MinResolutionHours,
    MAX(fst.ResolutionHours)                        AS MaxResolutionHours,

    -- CSAT
    AVG(CAST(fst.SatisfactionRating AS DECIMAL(5,2))) AS AvgCSAT,
    SUM(CASE WHEN fst.SatisfactionRating >= 4 THEN 1 ELSE 0 END) AS HighSatisfactionCount,

    -- Rate calculations
    CAST(SUM(CAST(fst.IsResolved AS INT)) AS DECIMAL(10,4))
        / NULLIF(COUNT(fst.TicketKey), 0) * 100    AS ResolutionRate_Pct,
    CAST(SUM(CAST(fst.IsEscalated AS INT)) AS DECIMAL(10,4))
        / NULLIF(COUNT(fst.TicketKey), 0) * 100    AS EscalationRate_Pct,

    -- SLA proxy: % resolved within 24 hours
    CAST(SUM(CASE WHEN fst.ResolutionHours <= 24 THEN 1 ELSE 0 END) AS DECIMAL(10,4))
        / NULLIF(SUM(CAST(fst.IsResolved AS INT)), 0) * 100 AS SLA24h_CompliancePct
FROM
    dbo.FactSupportTickets fst
    INNER JOIN dbo.DimDate     cd ON fst.CreatedDateKey      = cd.DateKey
    LEFT  JOIN dbo.DimEmployee de ON fst.AssignedEmployeeKey = de.EmployeeKey
GROUP BY
    cd.FullDate, cd.[Year], cd.QuarterLabel, cd.MonthYearLabel,
    de.FullName, de.Department, de.OfficeLocation,
    fst.Category, fst.Priority, fst.TicketStatus, fst.InboundChannel;
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. vw_CampaignROI
-- ─────────────────────────────────────────────────────────────────────────────
GO
CREATE OR ALTER VIEW dbo.vw_CampaignROI AS
SELECT
    -- Campaign attributes
    dc.CampaignKey                          AS CampaignKey,
    dc.CampaignName                         AS CampaignName,
    dc.CampaignType                         AS CampaignType,
    dc.TargetSegment                        AS TargetSegment,
    dc.Region                               AS Region,
    dc.CampaignStatus                       AS CampaignStatus,

    -- Date attributes
    sd.FullDate                             AS StartDate,
    ed.FullDate                             AS EndDate,
    sd.[Year]                               AS StartYear,
    sd.QuarterLabel                         AS StartQuarter,
    sd.MonthYearLabel                       AS StartMonthYear,

    -- Financial measures
    fcp.Budget                              AS Budget,
    fcp.Spend                               AS ActualSpend,
    fcp.Budget - fcp.Spend                  AS BudgetRemaining,
    fcp.BudgetUtilization_Pct               AS BudgetUtilization_Pct,
    fcp.RevenueGenerated                    AS RevenueGenerated,
    fcp.RevenueGenerated - fcp.Spend        AS NetReturn,
    fcp.ROI_Pct                             AS ROI_Pct,

    -- Engagement measures
    fcp.Impressions                         AS Impressions,
    fcp.Clicks                              AS Clicks,
    fcp.Conversions                         AS Conversions,
    fcp.CTR_Pct                             AS CTR_Pct,
    fcp.ConversionRate_Pct                  AS ConversionRate_Pct,
    fcp.CostPerClick                        AS CostPerClick,
    fcp.CostPerConversion                   AS CostPerConversion,
    fcp.DurationDays                        AS DurationDays,

    -- Efficiency label
    CASE
        WHEN fcp.ROI_Pct >= 200 THEN 'Excellent'
        WHEN fcp.ROI_Pct >= 100 THEN 'Good'
        WHEN fcp.ROI_Pct >= 0   THEN 'Break-Even'
        ELSE 'Loss'
    END                                     AS ROI_Band
FROM
    dbo.FactCampaignPerformance fcp
    INNER JOIN dbo.DimCampaign dc ON fcp.CampaignKey  = dc.CampaignKey
    INNER JOIN dbo.DimDate     sd ON fcp.StartDateKey = sd.DateKey
    INNER JOIN dbo.DimDate     ed ON fcp.EndDateKey   = ed.DateKey;
GO