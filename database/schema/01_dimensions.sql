-- =============================================================================
-- InsightHub — Dimension Tables (Star Schema)
-- File        : 01_dimensions.sql
-- Database    : Azure SQL  (insighthub-db)
-- Run order   : 1 of 6  (run before 02_facts.sql)
-- Description : Creates all six dimension tables.  Each table uses a surrogate
--               integer key as the primary key and stores the source UUID as an
--               alternate key (UNIQUE constraint) so the ETL can look up the
--               surrogate without a full-table scan.
--
-- Modeling decisions
-- ──────────────────
-- • SCD Type 1 on all dimensions (overwrite on change). SCD Type 2 can be
--   retrofitted in a later migration by adding EffectiveFrom/EffectiveTo
--   columns and a CurrentRecord flag — the pattern is stubbed on DimCustomer.
-- • DateKey uses INT in YYYYMMDD format (industry standard; avoids DATE joins).
-- • Fiscal year assumed to start April 1 (common SaaS convention).
-- • All text columns use NVARCHAR for Unicode support (customer names, cities).
-- • Status and code columns use VARCHAR (always ASCII, saves ~50 % storage).
-- • CHECK constraints enforce allowed values at the database layer so bad ETL
--   data fails loudly rather than silently corrupting reports.
-- =============================================================================

SET NOCOUNT ON;
PRINT '── InsightHub: creating dimension tables ──';

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. DimDate
--    Pre-populated by 03_populate_dim_date.sql.
--    Fact table FK columns always reference DateKey (INT, YYYYMMDD).
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.DimDate', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DimDate
    (
        -- Primary key: integer in YYYYMMDD format
        DateKey             INT         NOT NULL,

        -- Raw date value
        FullDate            DATE        NOT NULL,

        -- Day grain
        DayOfWeek           TINYINT     NOT NULL,   -- ISO: 1=Mon … 7=Sun
        DayName             VARCHAR(9)  NOT NULL,   -- 'Monday' … 'Sunday'
        DayOfMonth          TINYINT     NOT NULL,   -- 1–31
        DayOfYear           SMALLINT    NOT NULL,   -- 1–366

        -- Week grain
        WeekOfYear          TINYINT     NOT NULL,   -- ISO week 1–53

        -- Month grain
        MonthNumber         TINYINT     NOT NULL,   -- 1–12
        MonthName           VARCHAR(9)  NOT NULL,   -- 'January' … 'December'
        MonthShort          CHAR(3)     NOT NULL,   -- 'Jan' … 'Dec'
        YearMonth           INT         NOT NULL,   -- YYYYMM (useful for GROUP BY)
        MonthYearLabel      VARCHAR(8)  NOT NULL,   -- 'Jan 2024'

        -- Quarter grain
        Quarter             TINYINT     NOT NULL,   -- 1–4
        QuarterLabel        CHAR(2)     NOT NULL,   -- 'Q1' … 'Q4'

        -- Year grain
        [Year]              SMALLINT    NOT NULL,

        -- Weekend / holiday flags
        IsWeekend           BIT         NOT NULL    CONSTRAINT DF_DimDate_IsWeekend  DEFAULT 0,
        IsUSHoliday         BIT         NOT NULL    CONSTRAINT DF_DimDate_IsHoliday  DEFAULT 0,
        HolidayName         VARCHAR(50) NULL,

        -- Fiscal calendar (FY starts April 1)
        -- FY2024 = Apr 1 2023 → Mar 31 2024
        FiscalYear          SMALLINT    NOT NULL,   -- e.g. 2024
        FiscalQuarter       TINYINT     NOT NULL,   -- FQ1 = Apr-Jun, FQ4 = Jan-Mar
        FiscalMonth         TINYINT     NOT NULL,   -- FM1 = April … FM12 = March

        CONSTRAINT PK_DimDate PRIMARY KEY CLUSTERED (DateKey),
        CONSTRAINT UQ_DimDate_FullDate UNIQUE (FullDate),

        CONSTRAINT CK_DimDate_DayOfWeek   CHECK (DayOfWeek   BETWEEN 1 AND 7),
        CONSTRAINT CK_DimDate_DayOfMonth  CHECK (DayOfMonth  BETWEEN 1 AND 31),
        CONSTRAINT CK_DimDate_MonthNumber CHECK (MonthNumber BETWEEN 1 AND 12),
        CONSTRAINT CK_DimDate_Quarter     CHECK (Quarter     BETWEEN 1 AND 4)
    );
    PRINT '  ✓ DimDate created';
END
ELSE
    PRINT '  – DimDate already exists, skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. DimGeography
--    Stores the unique city/state/country combinations seen across orders.
--    Separate from DimCustomer so the same geography can serve multiple facts
--    (orders and, in future, warehouses, stores, employees).
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.DimGeography', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DimGeography
    (
        GeographyKey    INT             NOT NULL    IDENTITY(1,1),

        City            NVARCHAR(100)   NOT NULL,
        [State]         NVARCHAR(50)    NOT NULL    CONSTRAINT DF_DimGeo_State DEFAULT '',
        StateCode       CHAR(2)         NOT NULL    CONSTRAINT DF_DimGeo_StateCode DEFAULT '',
        Country         CHAR(2)         NOT NULL,   -- ISO 3166-1 alpha-2 (e.g. 'US')
        CountryName     NVARCHAR(60)    NOT NULL,
        -- Analytical rollup region (populated by ETL lookup)
        WorldRegion     VARCHAR(30)     NOT NULL    CONSTRAINT DF_DimGeo_Region DEFAULT 'Unknown',
        IsUSA           BIT             NOT NULL    CONSTRAINT DF_DimGeo_IsUSA DEFAULT 0,
        PostalCode      VARCHAR(20)     NULL,

        CONSTRAINT PK_DimGeography PRIMARY KEY CLUSTERED (GeographyKey),
        -- Business key: city + state + postal code
        CONSTRAINT UQ_DimGeography UNIQUE (City, StateCode, Country, PostalCode)
    );
    PRINT '  ✓ DimGeography created';
END
ELSE
    PRINT '  – DimGeography already exists, skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. DimCustomer
--    SCD Type 1 (overwrite).  RowInsertedDate / RowUpdatedDate / IsCurrentRecord
--    are retained as stubs so a future migration to SCD Type 2 only needs to add
--    EffectiveFrom / EffectiveTo columns without restructuring the table.
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.DimCustomer', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DimCustomer
    (
        CustomerKey         INT                 NOT NULL    IDENTITY(1,1),

        -- Source system natural key (UUID from generate_data.py)
        CustomerID          UNIQUEIDENTIFIER    NOT NULL,

        -- Personally Identifiable Information (PII)
        -- In production: consider column-level encryption or masking
        FirstName           NVARCHAR(50)        NOT NULL,
        LastName            NVARCHAR(50)        NOT NULL,
        FullName            NVARCHAR(101)       NOT NULL,   -- Stored, not computed, so ETL controls it
        Email               NVARCHAR(254)       NOT NULL,
        Phone               NVARCHAR(30)        NULL,

        -- Demographics
        DateOfBirth         DATE                NULL,
        AgeGroup            VARCHAR(5)          NULL,       -- '18-24', '25-34', …, '65+' (ETL-computed)
        RegistrationDate    DATE                NOT NULL,

        -- Segmentation (low-cardinality — used in RLS rules on Power BI)
        CustomerSegment     VARCHAR(10)         NOT NULL,
        AccountStatus       VARCHAR(15)         NOT NULL,

        -- Marketing
        MarketingOptIn      BIT                 NOT NULL    CONSTRAINT DF_DimCust_OptIn DEFAULT 0,
        PreferredChannel    VARCHAR(20)         NULL,
        ReferralSource      VARCHAR(30)         NULL,

        -- Financials (updated by ETL after each order load)
        LifetimeValue       DECIMAL(12, 2)      NOT NULL    CONSTRAINT DF_DimCust_LTV DEFAULT 0,

        -- SCD audit columns
        RowInsertedDate     DATETIME2(0)        NOT NULL    CONSTRAINT DF_DimCust_Inserted DEFAULT SYSUTCDATETIME(),
        RowUpdatedDate      DATETIME2(0)        NOT NULL    CONSTRAINT DF_DimCust_Updated  DEFAULT SYSUTCDATETIME(),
        IsCurrentRecord     BIT                 NOT NULL    CONSTRAINT DF_DimCust_Current  DEFAULT 1,

        CONSTRAINT PK_DimCustomer  PRIMARY KEY CLUSTERED (CustomerKey),
        CONSTRAINT AK_DimCustomer  UNIQUE (CustomerID),    -- ETL lookup key
        CONSTRAINT UQ_DimCust_Email UNIQUE (Email),

        CONSTRAINT CK_DimCust_Segment CHECK (CustomerSegment IN ('Bronze', 'Silver', 'Gold', 'Platinum')),
        CONSTRAINT CK_DimCust_Status  CHECK (AccountStatus   IN ('Active', 'Inactive', 'Suspended'))
    );
    PRINT '  ✓ DimCustomer created';
END
ELSE
    PRINT '  – DimCustomer already exists, skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. DimProduct
--    Grain: one row per active product SKU.
--    MarginPct is stored (not computed) so historical ETL loads preserve the
--    margin at the time of load, not the current margin.
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.DimProduct', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DimProduct
    (
        ProductKey      INT                 NOT NULL    IDENTITY(1,1),

        ProductID       UNIQUEIDENTIFIER    NOT NULL,
        ProductName     NVARCHAR(200)       NOT NULL,
        SKU             VARCHAR(20)         NOT NULL,
        Brand           NVARCHAR(100)       NOT NULL,

        -- Hierarchical attributes (enable drill-down in Power BI)
        Category        NVARCHAR(50)        NOT NULL,
        Subcategory     NVARCHAR(50)        NOT NULL,

        -- Pricing snapshot (values at time of last ETL load)
        UnitPrice       DECIMAL(10, 2)      NOT NULL,
        CostPrice       DECIMAL(10, 2)      NOT NULL,
        MarginPct       DECIMAL(5, 2)       NOT NULL,       -- (UnitPrice - CostPrice) / UnitPrice * 100

        -- Physical
        WeightKg        DECIMAL(8, 2)       NULL,

        -- Supply chain
        Supplier        NVARCHAR(150)       NULL,
        StockQuantity   INT                 NOT NULL    CONSTRAINT DF_DimProd_Stock DEFAULT 0,
        ReorderLevel    INT                 NOT NULL    CONSTRAINT DF_DimProd_Reorder DEFAULT 50,
        LaunchDate      DATE                NULL,

        -- Status
        ProductStatus   VARCHAR(15)         NOT NULL,

        -- Customer feedback
        Rating          DECIMAL(3, 1)       NULL,
        ReviewCount     INT                 NOT NULL    CONSTRAINT DF_DimProd_Reviews DEFAULT 0,

        -- Audit
        RowInsertedDate DATETIME2(0)        NOT NULL    CONSTRAINT DF_DimProd_Inserted DEFAULT SYSUTCDATETIME(),
        RowUpdatedDate  DATETIME2(0)        NOT NULL    CONSTRAINT DF_DimProd_Updated  DEFAULT SYSUTCDATETIME(),
        IsCurrentRecord BIT                 NOT NULL    CONSTRAINT DF_DimProd_Current  DEFAULT 1,

        CONSTRAINT PK_DimProduct     PRIMARY KEY CLUSTERED (ProductKey),
        CONSTRAINT AK_DimProduct_ID  UNIQUE (ProductID),
        CONSTRAINT AK_DimProduct_SKU UNIQUE (SKU),

        CONSTRAINT CK_DimProd_Status  CHECK (ProductStatus IN ('Active', 'Discontinued', 'Out of Stock')),
        CONSTRAINT CK_DimProd_Price   CHECK (UnitPrice > 0),
        CONSTRAINT CK_DimProd_Cost    CHECK (CostPrice > 0),
        CONSTRAINT CK_DimProd_Rating  CHECK (Rating BETWEEN 1.0 AND 5.0 OR Rating IS NULL)
    );
    PRINT '  ✓ DimProduct created';
END
ELSE
    PRINT '  – DimProduct already exists, skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. DimEmployee
--    Used as a role-player dimension: "AssignedEmployee" in FactSupportTickets.
--    ManagerEmployeeID stores the source UUID of the manager (not the surrogate
--    key) to avoid a circular FK dependency at table-creation time.
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.DimEmployee', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DimEmployee
    (
        EmployeeKey         INT                 NOT NULL    IDENTITY(1,1),

        EmployeeID          UNIQUEIDENTIFIER    NOT NULL,
        FirstName           NVARCHAR(50)        NOT NULL,
        LastName            NVARCHAR(50)        NOT NULL,
        FullName            NVARCHAR(101)       NOT NULL,
        Email               NVARCHAR(254)       NOT NULL,

        -- Organisational
        Department          NVARCHAR(50)        NOT NULL,
        Title               NVARCHAR(100)       NOT NULL,
        HireDate            DATE                NOT NULL,
        YearsAtCompany      DECIMAL(5, 1)       NOT NULL    CONSTRAINT DF_DimEmp_Years DEFAULT 0,
        OfficeLocation      NVARCHAR(50)        NULL,

        -- Compensation (store for HR analytics; mask in production via dynamic data masking)
        Salary              INT                 NOT NULL,

        -- Hierarchy — stores source UUID to enable self-join without circular FK
        ManagerEmployeeID   UNIQUEIDENTIFIER    NULL,

        -- Performance
        PerformanceRating   TINYINT             NOT NULL,
        EmployeeStatus      VARCHAR(15)         NOT NULL,

        -- Audit
        RowInsertedDate     DATETIME2(0)        NOT NULL    CONSTRAINT DF_DimEmp_Inserted DEFAULT SYSUTCDATETIME(),
        RowUpdatedDate      DATETIME2(0)        NOT NULL    CONSTRAINT DF_DimEmp_Updated  DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_DimEmployee  PRIMARY KEY CLUSTERED (EmployeeKey),
        CONSTRAINT AK_DimEmployee  UNIQUE (EmployeeID),
        CONSTRAINT UQ_DimEmp_Email UNIQUE (Email),

        CONSTRAINT CK_DimEmp_Status  CHECK (EmployeeStatus    IN ('Active', 'On Leave', 'Terminated')),
        CONSTRAINT CK_DimEmp_PerfRtg CHECK (PerformanceRating BETWEEN 1 AND 5),
        CONSTRAINT CK_DimEmp_Salary  CHECK (Salary > 0)
    );
    PRINT '  ✓ DimEmployee created';
END
ELSE
    PRINT '  – DimEmployee already exists, skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. DimCampaign
--    Stores campaign attributes.  Performance metrics (spend, impressions, ROI)
--    live in FactCampaignPerformance — dimension holds only descriptive data.
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.DimCampaign', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DimCampaign
    (
        CampaignKey     INT                 NOT NULL    IDENTITY(1,1),

        CampaignID      UNIQUEIDENTIFIER    NOT NULL,
        CampaignName    NVARCHAR(200)       NOT NULL,
        CampaignType    VARCHAR(30)         NOT NULL,
        TargetSegment   VARCHAR(30)         NOT NULL,
        Region          VARCHAR(30)         NOT NULL,
        DurationDays    INT                 NOT NULL,
        CampaignStatus  VARCHAR(15)         NOT NULL,

        -- Audit
        RowInsertedDate DATETIME2(0)        NOT NULL    CONSTRAINT DF_DimCampaign_Inserted DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_DimCampaign  PRIMARY KEY CLUSTERED (CampaignKey),
        CONSTRAINT AK_DimCampaign  UNIQUE (CampaignID),

        CONSTRAINT CK_DimCampaign_Type   CHECK (CampaignType   IN ('Email','Social Media','PPC','Display',
                                                                    'Content Marketing','TV','Radio','SMS','Affiliate')),
        CONSTRAINT CK_DimCampaign_Status CHECK (CampaignStatus IN ('Completed','Active','Paused','Cancelled','Planned'))
    );
    PRINT '  ✓ DimCampaign created';
END
ELSE
    PRINT '  – DimCampaign already exists, skipped';
GO

PRINT '── Dimension tables complete ──';
