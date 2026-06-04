-- =============================================================================
-- InsightHub — Performance Indexes
-- File        : 04_indexes.sql
-- Database    : Azure SQL  (insighthub-db)
-- Run order   : 4 of 6  (run AFTER 02_facts.sql)
-- Description : Creates all non-clustered B-tree and columnstore indexes.
--
-- Index strategy
-- ──────────────
-- FACT TABLES
--   • Every foreign key column gets a non-clustered B-tree index so the
--     query optimizer can efficiently navigate from fact → dimension.
--   • A non-clustered COLUMNSTORE index is added to each fact table.
--     Columnstore indexes compress data ~10× and accelerate analytical
--     (GROUP BY, SUM, COUNT) queries by 10–100× vs row-store.
--     Power BI DAX queries benefit enormously from columnstore.
--
-- DIMENSION TABLES
--   • Natural key columns (CustomerID, ProductID …) already have UNIQUE
--     constraints (which create unique indexes) — no duplicates needed.
--   • Frequently filtered low-cardinality columns get NC indexes so WHERE
--     clauses on CustomerSegment, Category, Department etc. avoid table scans.
--
-- Naming convention: IX_{Table}_{Columns}  /  CCI_{Table} (clustered columnstore)
-- =============================================================================

SET NOCOUNT ON;
PRINT '── InsightHub: creating performance indexes ──';

-- =============================================================================
-- FactSales indexes
-- =============================================================================

-- FK lookups — optimizer needs these to probe dimension tables efficiently
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FactSales_OrderDateKey')
    CREATE NONCLUSTERED INDEX IX_FactSales_OrderDateKey
        ON dbo.FactSales (OrderDateKey)
        INCLUDE (CustomerKey, ProductKey, GeographyKey, LineTotal, GrossRevenue, GrossProfit, Quantity);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FactSales_CustomerKey')
    CREATE NONCLUSTERED INDEX IX_FactSales_CustomerKey
        ON dbo.FactSales (CustomerKey)
        INCLUDE (OrderDateKey, ProductKey, LineTotal, GrossRevenue, GrossProfit, Quantity, OrderStatus);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FactSales_ProductKey')
    CREATE NONCLUSTERED INDEX IX_FactSales_ProductKey
        ON dbo.FactSales (ProductKey)
        INCLUDE (OrderDateKey, CustomerKey, LineTotal, GrossProfit, Quantity, DiscountAmount);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FactSales_GeographyKey')
    CREATE NONCLUSTERED INDEX IX_FactSales_GeographyKey
        ON dbo.FactSales (GeographyKey)
        INCLUDE (OrderDateKey, LineTotal, GrossRevenue, Quantity);

-- OrderID lookup — used by ETL to check if an order already exists (idempotency)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FactSales_OrderID')
    CREATE NONCLUSTERED INDEX IX_FactSales_OrderID
        ON dbo.FactSales (OrderID);

-- Date range + status queries (most common dashboard filter: "this month, completed orders")
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FactSales_Date_Status')
    CREATE NONCLUSTERED INDEX IX_FactSales_Date_Status
        ON dbo.FactSales (OrderDateKey, OrderStatus)
        INCLUDE (LineTotal, GrossRevenue, GrossProfit, Quantity, CustomerKey, ProductKey);

-- Columnstore — powers all Power BI aggregation queries
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'NCCI_FactSales')
    CREATE NONCLUSTERED COLUMNSTORE INDEX NCCI_FactSales
        ON dbo.FactSales
        (OrderDateKey, CustomerKey, ProductKey, GeographyKey,
         Quantity, LineTotal, DiscountAmount, ShippingAmount, TaxAmount,
         GrossRevenue, CostOfGoods, GrossProfit,
         OrderStatus, OrderChannel, PaymentMethod);

PRINT '  ✓ FactSales indexes created';

-- =============================================================================
-- FactSupportTickets indexes
-- =============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FST_CreatedDateKey')
    CREATE NONCLUSTERED INDEX IX_FST_CreatedDateKey
        ON dbo.FactSupportTickets (CreatedDateKey)
        INCLUDE (CustomerKey, AssignedEmployeeKey, Category, Priority,
                 TicketStatus, ResolutionHours, SatisfactionRating, IsEscalated, IsResolved);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FST_CustomerKey')
    CREATE NONCLUSTERED INDEX IX_FST_CustomerKey
        ON dbo.FactSupportTickets (CustomerKey)
        INCLUDE (CreatedDateKey, Category, Priority, TicketStatus, IsResolved, SatisfactionRating);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FST_EmployeeKey')
    CREATE NONCLUSTERED INDEX IX_FST_EmployeeKey
        ON dbo.FactSupportTickets (AssignedEmployeeKey)
        INCLUDE (CreatedDateKey, Category, Priority, IsResolved, ResolutionHours, SatisfactionRating);

-- Status filter — common dashboard query: "how many open tickets by priority?"
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FST_Status_Priority')
    CREATE NONCLUSTERED INDEX IX_FST_Status_Priority
        ON dbo.FactSupportTickets (TicketStatus, Priority)
        INCLUDE (CreatedDateKey, CustomerKey, AssignedEmployeeKey, ResolutionHours, IsEscalated);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'NCCI_FactSupportTickets')
    CREATE NONCLUSTERED COLUMNSTORE INDEX NCCI_FactSupportTickets
        ON dbo.FactSupportTickets
        (CreatedDateKey, CustomerKey, AssignedEmployeeKey,
         Category, Priority, TicketStatus,
         ResolutionHours, FirstResponseHours, SatisfactionRating,
         IsEscalated, IsResolved);

PRINT '  ✓ FactSupportTickets indexes created';

-- =============================================================================
-- FactCampaignPerformance indexes
-- =============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FCP_CampaignKey')
    CREATE NONCLUSTERED INDEX IX_FCP_CampaignKey
        ON dbo.FactCampaignPerformance (CampaignKey)
        INCLUDE (StartDateKey, EndDateKey, Budget, Spend, Impressions, Clicks,
                 Conversions, RevenueGenerated, ROI_Pct, BudgetUtilization_Pct);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FCP_StartDateKey')
    CREATE NONCLUSTERED INDEX IX_FCP_StartDateKey
        ON dbo.FactCampaignPerformance (StartDateKey)
        INCLUDE (CampaignKey, Spend, RevenueGenerated, Conversions, ROI_Pct);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'NCCI_FactCampaignPerformance')
    CREATE NONCLUSTERED COLUMNSTORE INDEX NCCI_FactCampaignPerformance
        ON dbo.FactCampaignPerformance
        (CampaignKey, StartDateKey, EndDateKey,
         Budget, Spend, Impressions, Clicks, Conversions,
         RevenueGenerated, ROI_Pct, CTR_Pct, ConversionRate_Pct,
         BudgetUtilization_Pct, DurationDays);

PRINT '  ✓ FactCampaignPerformance indexes created';

-- =============================================================================
-- DimCustomer indexes
-- =============================================================================

-- Segment filter — Power BI slicers and Row Level Security (RLS) both hit this
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DimCustomer_Segment')
    CREATE NONCLUSTERED INDEX IX_DimCustomer_Segment
        ON dbo.DimCustomer (CustomerSegment, AccountStatus)
        INCLUDE (CustomerKey, FullName, LifetimeValue, RegistrationDate);

-- Date filter — cohort analysis by registration month
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DimCustomer_RegDate')
    CREATE NONCLUSTERED INDEX IX_DimCustomer_RegDate
        ON dbo.DimCustomer (RegistrationDate)
        INCLUDE (CustomerKey, CustomerSegment, LifetimeValue);

PRINT '  ✓ DimCustomer indexes created';

-- =============================================================================
-- DimProduct indexes
-- =============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DimProduct_Category')
    CREATE NONCLUSTERED INDEX IX_DimProduct_Category
        ON dbo.DimProduct (Category, Subcategory, ProductStatus)
        INCLUDE (ProductKey, ProductName, Brand, UnitPrice, MarginPct, Rating);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DimProduct_Brand')
    CREATE NONCLUSTERED INDEX IX_DimProduct_Brand
        ON dbo.DimProduct (Brand)
        INCLUDE (ProductKey, Category, UnitPrice, MarginPct);

PRINT '  ✓ DimProduct indexes created';

-- =============================================================================
-- DimEmployee indexes
-- =============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DimEmployee_Dept')
    CREATE NONCLUSTERED INDEX IX_DimEmployee_Dept
        ON dbo.DimEmployee (Department, EmployeeStatus)
        INCLUDE (EmployeeKey, FullName, Title, PerformanceRating, Salary);

PRINT '  ✓ DimEmployee indexes created';

-- =============================================================================
-- DimDate indexes (calendar queries)
-- =============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DimDate_YearMonth')
    CREATE NONCLUSTERED INDEX IX_DimDate_YearMonth
        ON dbo.DimDate (YearMonth)
        INCLUDE (DateKey, FullDate, [Year], Quarter, MonthNumber, MonthYearLabel, FiscalYear, FiscalQuarter);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DimDate_FiscalYear')
    CREATE NONCLUSTERED INDEX IX_DimDate_FiscalYear
        ON dbo.DimDate (FiscalYear, FiscalQuarter, FiscalMonth)
        INCLUDE (DateKey, FullDate, [Year], Quarter);

PRINT '  ✓ DimDate indexes created';
PRINT '── All indexes created ──';
