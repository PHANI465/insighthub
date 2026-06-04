-- =============================================================================
-- InsightHub — Fact Tables (Star Schema)
-- File        : 02_facts.sql
-- Database    : Azure SQL  (insighthub-db)
-- Run order   : 2 of 6  (run AFTER 01_dimensions.sql)
-- Description : Creates the three fact tables that form the measurable core of
--               InsightHub's analytics layer.
--
-- Fact table grains
-- ─────────────────
-- FactSales               : one row per order LINE ITEM  (finest grain available)
-- FactSupportTickets      : one row per support ticket
-- FactCampaignPerformance : one row per marketing campaign
--
-- Design notes
-- ────────────
-- • Clustered index on the surrogate BIGINT/INT key — Azure SQL default.
-- • Non-clustered indexes are created in 04_indexes.sql to keep this file clean.
-- • Degenerate dimensions (OrderID, TicketID) are stored as UNIQUEIDENTIFIER
--   columns directly in the fact — no separate bridge table needed.
-- • ShippedDateKey / DeliveredDateKey are nullable FKs to DimDate because not
--   every order status produces shipping events.
-- • BIGINT surrogate on FactSales because 50k orders × avg 3 items = 150k rows
--   today; multiplicative growth over years pushes well past INT range.
-- =============================================================================

SET NOCOUNT ON;
PRINT '── InsightHub: creating fact tables ──';

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. FactSales
--    Grain   : one row per order line item
--    Additive measures: Quantity, LineTotal, DiscountAmount, ShippingAmount,
--                       TaxAmount, GrossRevenue, GrossProfit
--    Semi-additive: none at this grain
--    Non-additive: UnitPrice, DiscountPct (ratios — never SUM across rows)
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.FactSales', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.FactSales
    (
        -- Surrogate key (BIGINT to support future growth)
        SalesKey            BIGINT              NOT NULL    IDENTITY(1,1),

        -- ── Foreign keys to dimension tables ────────────────────────────────
        OrderDateKey        INT                 NOT NULL,   -- FK → DimDate
        CustomerKey         INT                 NOT NULL,   -- FK → DimCustomer
        ProductKey          INT                 NOT NULL,   -- FK → DimProduct
        GeographyKey        INT                 NOT NULL,   -- FK → DimGeography
        ShippedDateKey      INT                 NULL,       -- FK → DimDate (nullable)
        DeliveredDateKey    INT                 NULL,       -- FK → DimDate (nullable)

        -- ── Degenerate dimensions (no lookup table needed) ───────────────────
        OrderID             UNIQUEIDENTIFIER    NOT NULL,
        LineItemID          UNIQUEIDENTIFIER    NOT NULL,

        -- ── Descriptive attributes (low-cardinality; stored here for simplicity) ─
        OrderStatus         VARCHAR(15)         NOT NULL,
        PaymentMethod       VARCHAR(20)         NOT NULL,
        OrderChannel        VARCHAR(15)         NOT NULL,

        -- ── Additive measures ────────────────────────────────────────────────
        Quantity            INT                 NOT NULL    CONSTRAINT CK_FS_Qty       CHECK (Quantity > 0),
        DiscountAmount      DECIMAL(10, 2)      NOT NULL    CONSTRAINT DF_FS_Disc      DEFAULT 0,
        LineTotal           DECIMAL(12, 2)      NOT NULL,   -- unit_price*qty - discount
        -- Order-level costs prorated to each line item by ETL
        ShippingAmount      DECIMAL(10, 2)      NOT NULL    CONSTRAINT DF_FS_Ship      DEFAULT 0,
        TaxAmount           DECIMAL(10, 2)      NOT NULL    CONSTRAINT DF_FS_Tax       DEFAULT 0,
        GrossRevenue        DECIMAL(12, 2)      NOT NULL,   -- LineTotal + Shipping + Tax
        CostOfGoods         DECIMAL(12, 2)      NOT NULL,   -- CostPrice * Quantity (from DimProduct at load time)
        GrossProfit         DECIMAL(12, 2)      NOT NULL,   -- GrossRevenue - CostOfGoods

        -- ── Non-additive measures (store for point lookups; never SUM) ───────
        UnitPrice           DECIMAL(10, 2)      NOT NULL,
        DiscountPct         TINYINT             NOT NULL    CONSTRAINT DF_FS_DiscPct   DEFAULT 0,

        -- ── Audit ────────────────────────────────────────────────────────────
        RowInsertedDate     DATETIME2(0)        NOT NULL    CONSTRAINT DF_FS_Inserted  DEFAULT SYSUTCDATETIME(),

        -- ── Primary key ──────────────────────────────────────────────────────
        CONSTRAINT PK_FactSales         PRIMARY KEY CLUSTERED (SalesKey),
        CONSTRAINT AK_FactSales_LineItem UNIQUE (LineItemID),      -- idempotent ETL upsert

        -- ── Referential integrity ─────────────────────────────────────────────
        CONSTRAINT FK_FactSales_OrderDate    FOREIGN KEY (OrderDateKey)     REFERENCES dbo.DimDate      (DateKey),
        CONSTRAINT FK_FactSales_Customer     FOREIGN KEY (CustomerKey)      REFERENCES dbo.DimCustomer  (CustomerKey),
        CONSTRAINT FK_FactSales_Product      FOREIGN KEY (ProductKey)       REFERENCES dbo.DimProduct   (ProductKey),
        CONSTRAINT FK_FactSales_Geography    FOREIGN KEY (GeographyKey)     REFERENCES dbo.DimGeography (GeographyKey),
        CONSTRAINT FK_FactSales_ShipDate     FOREIGN KEY (ShippedDateKey)   REFERENCES dbo.DimDate      (DateKey),
        CONSTRAINT FK_FactSales_DelivDate    FOREIGN KEY (DeliveredDateKey) REFERENCES dbo.DimDate      (DateKey),

        -- ── Business rules ────────────────────────────────────────────────────
        CONSTRAINT CK_FS_Status     CHECK (OrderStatus  IN ('Completed','Shipped','Pending','Cancelled','Returned')),
        CONSTRAINT CK_FS_Channel    CHECK (OrderChannel IN ('Online','Mobile App','In-Store','Phone')),
        CONSTRAINT CK_FS_DiscPct    CHECK (DiscountPct  BETWEEN 0 AND 100)
    );
    PRINT '  ✓ FactSales created';
END
ELSE
    PRINT '  – FactSales already exists, skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. FactSupportTickets
--    Grain   : one row per support ticket (not per interaction/comment)
--    Additive: ResolutionHours, FirstResponseHours, IsEscalated, IsResolved
--    Non-additive: SatisfactionRating (average is meaningful, sum is not)
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.FactSupportTickets', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.FactSupportTickets
    (
        TicketKey               INT                 NOT NULL    IDENTITY(1,1),

        -- ── Foreign keys ─────────────────────────────────────────────────────
        CreatedDateKey          INT                 NOT NULL,   -- FK → DimDate
        ResolvedDateKey         INT                 NULL,       -- FK → DimDate (NULL if open)
        CustomerKey             INT                 NOT NULL,   -- FK → DimCustomer
        AssignedEmployeeKey     INT                 NULL,       -- FK → DimEmployee (NULL if unassigned)

        -- ── Degenerate dimension ─────────────────────────────────────────────
        TicketID                UNIQUEIDENTIFIER    NOT NULL,

        -- ── Descriptive attributes ────────────────────────────────────────────
        Category                VARCHAR(20)         NOT NULL,
        Priority                VARCHAR(10)         NOT NULL,
        TicketStatus            VARCHAR(20)         NOT NULL,
        InboundChannel          VARCHAR(25)         NOT NULL,

        -- ── Additive measures ────────────────────────────────────────────────
        ResolutionHours         DECIMAL(8, 1)       NULL,       -- NULL for open tickets
        FirstResponseHours      DECIMAL(6, 2)       NULL,
        IsEscalated             BIT                 NOT NULL    CONSTRAINT DF_FST_Escalated DEFAULT 0,
        IsResolved              BIT                 NOT NULL    CONSTRAINT DF_FST_Resolved  DEFAULT 0,

        -- ── Non-additive measures ─────────────────────────────────────────────
        SatisfactionRating      TINYINT             NULL,       -- 1–5; NULL until resolved

        -- ── Audit ─────────────────────────────────────────────────────────────
        RowInsertedDate         DATETIME2(0)        NOT NULL    CONSTRAINT DF_FST_Inserted  DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_FactSupportTickets    PRIMARY KEY CLUSTERED (TicketKey),
        CONSTRAINT AK_FactTickets_TicketID  UNIQUE (TicketID),

        CONSTRAINT FK_FST_CreatedDate   FOREIGN KEY (CreatedDateKey)      REFERENCES dbo.DimDate     (DateKey),
        CONSTRAINT FK_FST_ResolvedDate  FOREIGN KEY (ResolvedDateKey)     REFERENCES dbo.DimDate     (DateKey),
        CONSTRAINT FK_FST_Customer      FOREIGN KEY (CustomerKey)         REFERENCES dbo.DimCustomer (CustomerKey),
        CONSTRAINT FK_FST_Employee      FOREIGN KEY (AssignedEmployeeKey) REFERENCES dbo.DimEmployee (EmployeeKey),

        CONSTRAINT CK_FST_Category   CHECK (Category  IN ('Billing','Technical','Shipping','Returns','General')),
        CONSTRAINT CK_FST_Priority   CHECK (Priority  IN ('Low','Medium','High','Critical')),
        CONSTRAINT CK_FST_Status     CHECK (TicketStatus IN ('Open','In Progress','Resolved','Closed','Escalated')),
        CONSTRAINT CK_FST_SatRating  CHECK (SatisfactionRating BETWEEN 1 AND 5 OR SatisfactionRating IS NULL),
        CONSTRAINT CK_FST_ResHours   CHECK (ResolutionHours IS NULL OR ResolutionHours >= 0)
    );
    PRINT '  ✓ FactSupportTickets created';
END
ELSE
    PRINT '  – FactSupportTickets already exists, skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. FactCampaignPerformance
--    Grain   : one row per marketing campaign
--    All measures are fully additive (can SUM across segments, regions, types).
--    Exception: ROI_Pct and rate metrics — stored for convenience but must be
--    re-derived (weighted average) when aggregating across campaigns.
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.FactCampaignPerformance', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.FactCampaignPerformance
    (
        CampaignPerfKey         INT                 NOT NULL    IDENTITY(1,1),

        -- ── Foreign keys ─────────────────────────────────────────────────────
        CampaignKey             INT                 NOT NULL,   -- FK → DimCampaign
        StartDateKey            INT                 NOT NULL,   -- FK → DimDate
        EndDateKey              INT                 NOT NULL,   -- FK → DimDate

        -- ── Degenerate dimension ─────────────────────────────────────────────
        CampaignID              UNIQUEIDENTIFIER    NOT NULL,

        -- ── Additive measures ─────────────────────────────────────────────────
        Budget                  DECIMAL(14, 2)      NOT NULL    CONSTRAINT CK_FCP_Budget CHECK (Budget >= 0),
        Spend                   DECIMAL(14, 2)      NOT NULL    CONSTRAINT CK_FCP_Spend  CHECK (Spend  >= 0),
        Impressions             INT                 NOT NULL    CONSTRAINT CK_FCP_Impr   CHECK (Impressions >= 0),
        Clicks                  INT                 NOT NULL    CONSTRAINT CK_FCP_Clicks CHECK (Clicks >= 0),
        Conversions             INT                 NOT NULL    CONSTRAINT CK_FCP_Conv   CHECK (Conversions >= 0),
        RevenueGenerated        DECIMAL(14, 2)      NOT NULL    CONSTRAINT CK_FCP_Rev    CHECK (RevenueGenerated >= 0),
        DurationDays            INT                 NOT NULL    CONSTRAINT CK_FCP_Dur    CHECK (DurationDays > 0),

        -- ── Derived / non-additive measures (stored for single-campaign reports) ─
        ROI_Pct                 DECIMAL(8, 2)       NOT NULL,   -- (Revenue - Spend) / Spend * 100
        CTR_Pct                 DECIMAL(8, 3)       NOT NULL,   -- Clicks / Impressions * 100
        ConversionRate_Pct      DECIMAL(8, 3)       NOT NULL,   -- Conversions / Clicks * 100
        CostPerClick            DECIMAL(10, 4)      NOT NULL    CONSTRAINT DF_FCP_CPC DEFAULT 0,
        CostPerConversion       DECIMAL(10, 2)      NOT NULL    CONSTRAINT DF_FCP_CPConv DEFAULT 0,
        BudgetUtilization_Pct   DECIMAL(8, 2)       NOT NULL,   -- Spend / Budget * 100

        -- ── Audit ─────────────────────────────────────────────────────────────
        RowInsertedDate         DATETIME2(0)        NOT NULL    CONSTRAINT DF_FCP_Inserted DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_FactCampaignPerf      PRIMARY KEY CLUSTERED (CampaignPerfKey),
        CONSTRAINT AK_FactCampaign_ID       UNIQUE (CampaignID),

        CONSTRAINT FK_FCP_Campaign   FOREIGN KEY (CampaignKey)  REFERENCES dbo.DimCampaign (CampaignKey),
        CONSTRAINT FK_FCP_StartDate  FOREIGN KEY (StartDateKey) REFERENCES dbo.DimDate     (DateKey),
        CONSTRAINT FK_FCP_EndDate    FOREIGN KEY (EndDateKey)   REFERENCES dbo.DimDate     (DateKey)
    );
    PRINT '  ✓ FactCampaignPerformance created';
END
ELSE
    PRINT '  – FactCampaignPerformance already exists, skipped';
GO

PRINT '── Fact tables complete ──';
