-- =============================================================================
-- InsightHub — Master Schema Runner
-- File        : run_all.sql
-- Description : Execute this script in SSMS or sqlcmd to deploy the full
--               InsightHub star schema to Azure SQL in the correct order.
--
-- Prerequisites
-- ─────────────
-- 1. You are connected to the correct Azure SQL database (insighthub-db).
--    Run: SELECT DB_NAME();  to confirm before executing.
-- 2. The login has db_owner or ddl_admin role on the database.
--
-- Execution options
-- ─────────────────
-- Option A — SSMS: Open this file → set connection to insighthub-db → Execute.
-- Option B — sqlcmd:
--   sqlcmd -S <server>.database.windows.net -d insighthub-db -U <user> -P <pwd> \
--          -i database/schema/run_all.sql
-- Option C — Python runner (preferred for CI/CD):
--   python database/run_schema.py
-- =============================================================================

-- Safety check: confirm we are on the correct database
DECLARE @dbName SYSNAME = DB_NAME();
IF @dbName NOT LIKE '%insighthub%'
BEGIN
    RAISERROR(
        'Wrong database! Currently connected to "%s". Connect to insighthub-db before running.',
        16, 1, @dbName
    );
    RETURN;
END
PRINT 'Connected to: ' + @dbName;
PRINT '══════════════════════════════════════════════════════════════════';
PRINT '  InsightHub — Full Schema Deployment';
PRINT '  Started : ' + CONVERT(VARCHAR(25), SYSDATETIME(), 121);
PRINT '══════════════════════════════════════════════════════════════════';

-- ── File 1: Dimension tables ────────────────────────────────────────────────
PRINT '';
PRINT '[ 1/5 ] Dimension tables …';
:r database/schema/01_dimensions.sql

-- ── File 2: Fact tables ─────────────────────────────────────────────────────
PRINT '';
PRINT '[ 2/5 ] Fact tables …';
:r database/schema/02_facts.sql

-- ── File 3: Populate DimDate ────────────────────────────────────────────────
PRINT '';
PRINT '[ 3/5 ] Populating DimDate …';
:r database/schema/03_populate_dim_date.sql

-- ── File 4: Performance indexes ─────────────────────────────────────────────
PRINT '';
PRINT '[ 4/5 ] Performance indexes …';
:r database/schema/04_indexes.sql

-- ── File 5: Reporting views ─────────────────────────────────────────────────
PRINT '';
PRINT '[ 5/5 ] Reporting views …';
:r database/schema/05_views.sql

PRINT '';
PRINT '══════════════════════════════════════════════════════════════════';
PRINT '  ✅  InsightHub schema deployed successfully.';
PRINT '  Finished : ' + CONVERT(VARCHAR(25), SYSDATETIME(), 121);
PRINT '══════════════════════════════════════════════════════════════════';
PRINT '';
PRINT 'Next step: run python database/run_schema.py --verify to confirm';
PRINT 'all tables, indexes, and views exist in the correct state.';
