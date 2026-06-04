-- =============================================================================
-- InsightHub — Migration 001: Initial Star Schema
-- File        : database/migrations/001_initial_schema.sql
-- Date        : 2026-06-03
-- Author      : Phani465
-- Description : Baseline migration that records the initial schema deployment.
--               The actual DDL is in database/schema/01_dimensions.sql through
--               database/schema/05_views.sql.  This file serves as the
--               migration history record and can be re-run safely (idempotent).
--
-- Migration log table (created on first run if not present)
-- ──────────────────────────────────────────────────────────
-- dbo.SchemaVersion tracks every migration applied to this database so the
-- Python runner can skip already-applied migrations in future deployments.
-- =============================================================================

SET NOCOUNT ON;

-- Create migration history table if it does not exist
IF OBJECT_ID('dbo.SchemaVersion', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.SchemaVersion
    (
        VersionID       INT             NOT NULL    IDENTITY(1,1),
        MigrationName   VARCHAR(200)    NOT NULL,
        AppliedDate     DATETIME2(0)    NOT NULL    DEFAULT SYSUTCDATETIME(),
        AppliedBy       SYSNAME         NOT NULL    DEFAULT SUSER_SNAME(),
        Description     NVARCHAR(500)   NULL,
        CONSTRAINT PK_SchemaVersion     PRIMARY KEY CLUSTERED (VersionID),
        CONSTRAINT UQ_SchemaVersion     UNIQUE (MigrationName)
    );
    PRINT 'Created dbo.SchemaVersion migration history table.';
END

-- Record this migration (skip if already recorded)
IF NOT EXISTS (SELECT 1 FROM dbo.SchemaVersion WHERE MigrationName = '001_initial_schema')
BEGIN
    INSERT INTO dbo.SchemaVersion (MigrationName, Description)
    VALUES (
        '001_initial_schema',
        'Initial star schema: 6 dimension tables (DimDate, DimGeography, DimCustomer, ' +
        'DimProduct, DimEmployee, DimCampaign), 3 fact tables (FactSales, ' +
        'FactSupportTickets, FactCampaignPerformance), 5 reporting views, ' +
        'DimDate populated 2017-2030 with US federal holidays.'
    );
    PRINT 'Migration 001_initial_schema recorded in dbo.SchemaVersion.';
END
ELSE
    PRINT 'Migration 001_initial_schema already recorded — skipped.';

-- Verify object counts
DECLARE @tableCount INT, @viewCount INT, @indexCount INT;
SELECT @tableCount = COUNT(*) FROM sys.tables WHERE schema_id = SCHEMA_ID('dbo') AND name LIKE 'Dim%' OR name LIKE 'Fact%';
SELECT @viewCount  = COUNT(*) FROM sys.views  WHERE schema_id = SCHEMA_ID('dbo') AND name LIKE 'vw_%';
SELECT @indexCount = COUNT(*) FROM sys.indexes i
    INNER JOIN sys.tables t ON i.object_id = t.object_id
    WHERE t.schema_id = SCHEMA_ID('dbo') AND i.type IN (5, 6);  -- 5=CCI, 6=NCCI

PRINT 'Schema summary after 001:';
PRINT '  Dim/Fact tables : ' + CAST(@tableCount AS VARCHAR);
PRINT '  Reporting views : ' + CAST(@viewCount  AS VARCHAR);
PRINT '  Columnstore idx : ' + CAST(@indexCount AS VARCHAR);
