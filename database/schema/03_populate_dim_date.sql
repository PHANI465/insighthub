-- =============================================================================
-- InsightHub — Populate DimDate
-- File        : 03_populate_dim_date.sql
-- Database    : Azure SQL  (insighthub-db)
-- Run order   : 3 of 6  (run AFTER 01_dimensions.sql)
-- Description : Populates dbo.DimDate for the date range 2017-01-01 to
--               2030-12-31 (~4,749 rows) using a cross-join tally table
--               (no recursion, avoids MAXRECURSION limit).
--               Then marks all US federal holidays for every year in range.
--               Idempotent: skips population if rows already exist.
--
-- Tally table technique
-- ─────────────────────
-- Cross-joining small CTEs doubles row count at each step:
--   E2(2) → E4(4) → E16(16) → E256(256) → E4K(4,096) → E8K(8,192)
-- 8,192 > 4,749 required rows — covers the full range with zero recursion.
--
-- Fiscal year convention (starts April 1)
-- ───────────────────────────────────────
-- FY2024 = April 1 2023 → March 31 2024
--   FiscalYear  : calendar year + 1 if month ≥ April, else calendar year
--   FiscalMonth : month - 3 if month ≥ April, else month + 9  (April = FM1)
--   FiscalQtr   : CEILING(FiscalMonth / 3.0)
--
-- US Holiday floating-date formula
-- ─────────────────────────────────
-- Anchor: 2000-01-03 was a known Monday.
-- ISO weekday offset from anchor = DATEDIFF(DAY, '2000-01-03', date) % 7
--   0=Mon  1=Tue  2=Wed  3=Thu  4=Fri  5=Sat  6=Sun
-- First weekday W of month M:
--   offset = ( W - DATEDIFF(DAY,'2000-01-03', DATEFROMPARTS(y,M,1)) % 7 + 7 ) % 7
--   first_W = DATEADD(DAY, offset, DATEFROMPARTS(y,M,1))
-- Nth occurrence: DATEADD(DAY, (N-1)*7, first_W)
-- Last Monday of month:  first Monday of next month − 7 days
-- =============================================================================

SET NOCOUNT ON;
PRINT '── InsightHub: populating DimDate ──';

-- Idempotency guard: skip if data already exists
IF EXISTS (SELECT 1 FROM dbo.DimDate)
BEGIN
    PRINT '  DimDate already has rows — skipping population.';
    PRINT '  To re-populate: TRUNCATE TABLE dbo.DimDate; then re-run this script.';
END
ELSE
BEGIN
    -- ── Step 1: declare date range ──────────────────────────────────────────
    DECLARE @RangeStart DATE = '20170101';
    DECLARE @RangeEnd   DATE = '20301231';
    DECLARE @Inserted   INT;

    -- ── Step 2: insert all calendar rows ────────────────────────────────────
    ;WITH
    E2    AS (SELECT 1 AS n UNION ALL SELECT 1),
    E4    AS (SELECT 1 AS n FROM E2    a CROSS JOIN E2    b),
    E16   AS (SELECT 1 AS n FROM E4    a CROSS JOIN E4    b),
    E256  AS (SELECT 1 AS n FROM E16   a CROSS JOIN E16   b),
    E4K   AS (SELECT 1 AS n FROM E256  a CROSS JOIN E16   b),
    E8K   AS (SELECT 1 AS n FROM E4K   a CROSS JOIN E2    b),
    Tally AS
    (
        SELECT ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS n
        FROM E8K
    ),
    DateRange AS
    (
        SELECT DATEADD(DAY, n, @RangeStart) AS d
        FROM Tally
        WHERE n <= DATEDIFF(DAY, @RangeStart, @RangeEnd)
    ),
    DateCalc AS
    (
        SELECT
            d,
            CONVERT(INT, CONVERT(VARCHAR(8), d, 112))                           AS DateKey,
            -- ISO weekday (1=Mon…7=Sun) using 2000-01-03 anchor (known Monday)
            (DATEDIFF(DAY, CAST('2000-01-03' AS DATE), d) % 7) + 1             AS DayOfWeekISO,
            DATENAME(WEEKDAY, d)                                                AS DayName,
            DAY(d)                                                              AS DayOfMonth,
            DATEPART(DAYOFYEAR, d)                                              AS DayOfYear,
            DATEPART(ISO_WEEK, d)                                               AS WeekOfYear,
            MONTH(d)                                                            AS MonthNumber,
            DATENAME(MONTH, d)                                                  AS MonthName,
            LEFT(DATENAME(MONTH, d), 3)                                         AS MonthShort,
            YEAR(d) * 100 + MONTH(d)                                            AS YearMonth,
            LEFT(DATENAME(MONTH, d), 3) + ' ' + CAST(YEAR(d) AS VARCHAR(4))    AS MonthYearLabel,
            DATEPART(QUARTER, d)                                                AS Quarter,
            YEAR(d)                                                             AS CalYear,
            -- Weekend: ISO 6=Sat, 7=Sun
            CASE WHEN (DATEDIFF(DAY, CAST('2000-01-03' AS DATE), d) % 7) + 1
                      IN (6, 7) THEN 1 ELSE 0 END                              AS IsWeekend,
            -- Fiscal year (April start)
            CASE WHEN MONTH(d) >= 4 THEN YEAR(d) + 1 ELSE YEAR(d) END         AS FiscalYear,
            CASE WHEN MONTH(d) >= 4 THEN MONTH(d) - 3 ELSE MONTH(d) + 9 END   AS FiscalMonth
        FROM DateRange
    )
    INSERT INTO dbo.DimDate
    (
        DateKey,  FullDate,
        DayOfWeek, DayName, DayOfMonth, DayOfYear,
        WeekOfYear,
        MonthNumber, MonthName, MonthShort, YearMonth, MonthYearLabel,
        Quarter, QuarterLabel, [Year],
        IsWeekend, IsUSHoliday, HolidayName,
        FiscalYear, FiscalQuarter, FiscalMonth
    )
    SELECT
        DateKey,
        d,
        DayOfWeekISO,
        DayName,
        DayOfMonth,
        DayOfYear,
        WeekOfYear,
        MonthNumber,
        MonthName,
        MonthShort,
        YearMonth,
        MonthYearLabel,
        Quarter,
        'Q' + CAST(Quarter AS CHAR(1)),
        CalYear,
        IsWeekend,
        0,      -- IsUSHoliday — updated in Step 3
        NULL,   -- HolidayName  — updated in Step 3
        FiscalYear,
        CEILING(FiscalMonth / 3.0),
        FiscalMonth
    FROM DateCalc
    ORDER BY DateKey;

    SET @Inserted = @@ROWCOUNT;
    PRINT '  ✓ Inserted ' + CAST(@Inserted AS VARCHAR) + ' date rows (2017-01-01 → 2030-12-31)';

    -- ── Step 3: mark US federal holidays ────────────────────────────────────
    -- Anchor Monday for ISO offset: 2000-01-03
    ;WITH
    YearList AS
    (
        SELECT DISTINCT [Year] AS y FROM dbo.DimDate
    ),
    -- Helper CTE: first occurrence of weekday W (0=Mon…6=Sun) in a given month
    -- Returns the date of first_W for each year+month combination below
    Holidays AS
    (
        -- ── Fixed-date holidays ──────────────────────────────────────────────
        SELECT y, DATEFROMPARTS(y,  1,  1) AS hDate, 'New Year''s Day'         AS hName FROM YearList
        UNION ALL
        SELECT y, DATEFROMPARTS(y,  7,  4),           'Independence Day'                 FROM YearList
        UNION ALL
        SELECT y, DATEFROMPARTS(y, 11, 11),           'Veterans Day'                     FROM YearList
        UNION ALL
        SELECT y, DATEFROMPARTS(y, 12, 25),           'Christmas Day'                    FROM YearList

        UNION ALL
        -- ── Floating holidays ─────────────────────────────────────────────────
        -- MLK Day: 3rd Monday of January  [W=0, N=3 → offset 14]
        SELECT y,
            DATEADD(DAY, 14,    -- (3-1)*7 = skip to 3rd occurrence
                DATEADD(DAY,
                    (0 - DATEDIFF(DAY, CAST('2000-01-03' AS DATE),
                                       DATEFROMPARTS(y, 1, 1)) % 7 + 7) % 7,
                    DATEFROMPARTS(y, 1, 1))
            ),
            'Martin Luther King Jr. Day'
        FROM YearList

        UNION ALL
        -- Presidents Day: 3rd Monday of February  [W=0, N=3]
        SELECT y,
            DATEADD(DAY, 14,
                DATEADD(DAY,
                    (0 - DATEDIFF(DAY, CAST('2000-01-03' AS DATE),
                                       DATEFROMPARTS(y, 2, 1)) % 7 + 7) % 7,
                    DATEFROMPARTS(y, 2, 1))
            ),
            'Presidents'' Day'
        FROM YearList

        UNION ALL
        -- Memorial Day: LAST Monday of May = first Monday of June − 7
        SELECT y,
            DATEADD(DAY, -7,
                DATEADD(DAY,
                    (0 - DATEDIFF(DAY, CAST('2000-01-03' AS DATE),
                                       DATEFROMPARTS(y, 6, 1)) % 7 + 7) % 7,
                    DATEFROMPARTS(y, 6, 1))
            ),
            'Memorial Day'
        FROM YearList

        UNION ALL
        -- Juneteenth: June 19 (federal since 2021)
        SELECT y, DATEFROMPARTS(y, 6, 19), 'Juneteenth National Independence Day'
        FROM YearList WHERE y >= 2021

        UNION ALL
        -- Labor Day: 1st Monday of September  [W=0, N=1 → offset 0]
        SELECT y,
            DATEADD(DAY,
                (0 - DATEDIFF(DAY, CAST('2000-01-03' AS DATE),
                                   DATEFROMPARTS(y, 9, 1)) % 7 + 7) % 7,
                DATEFROMPARTS(y, 9, 1)
            ),
            'Labor Day'
        FROM YearList

        UNION ALL
        -- Columbus Day: 2nd Monday of October  [W=0, N=2 → offset 7]
        SELECT y,
            DATEADD(DAY, 7,
                DATEADD(DAY,
                    (0 - DATEDIFF(DAY, CAST('2000-01-03' AS DATE),
                                       DATEFROMPARTS(y, 10, 1)) % 7 + 7) % 7,
                    DATEFROMPARTS(y, 10, 1))
            ),
            'Columbus Day'
        FROM YearList

        UNION ALL
        -- Thanksgiving: 4th Thursday of November  [W=3 (Thu), N=4 → offset 21]
        SELECT y,
            DATEADD(DAY, 21,
                DATEADD(DAY,
                    (3 - DATEDIFF(DAY, CAST('2000-01-03' AS DATE),
                                       DATEFROMPARTS(y, 11, 1)) % 7 + 7) % 7,
                    DATEFROMPARTS(y, 11, 1))
            ),
            'Thanksgiving Day'
        FROM YearList
    )
    UPDATE d
    SET
        d.IsUSHoliday = 1,
        d.HolidayName = h.hName
    FROM dbo.DimDate d
    INNER JOIN Holidays h ON d.FullDate = h.hDate;

    PRINT '  ✓ US federal holidays marked: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' dates';
    PRINT '── DimDate population complete ──';
END
GO
