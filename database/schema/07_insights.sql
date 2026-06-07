-- =============================================================================
-- InsightHub — AI Insights Storage
-- File        : 07_insights.sql
-- Database    : Azure SQL  (insighthub-db)
-- Run order   : 7 of 7  (run AFTER all dimensions, facts, views, app_users)
-- Description : Persistent storage for GPT-4o generated business narratives.
--               The insights engine (Phase 7) writes here; the FastAPI backend
--               reads here to serve GET /api/insights.
--
-- Schema decisions
-- ─────────────────
-- • UNIQUEIDENTIFIER PK: avoids integer sequence management; IDs are generated
--   in Python (uuid.uuid4()) before INSERT so no SCOPE_IDENTITY() needed.
-- • StructuredJson / MetricsJson stored as NVARCHAR(MAX): Azure SQL supports
--   JSON path queries (JSON_VALUE, OPENJSON) on these columns if needed later.
-- • ConfidenceScore DECIMAL(4,3): 0.000–1.000, computed from data completeness
--   (fraction of expected metric fields that are non-null / non-zero).
-- • Idempotent: safe to re-run via IF OBJECT_ID guard.
-- =============================================================================

SET NOCOUNT ON;
GO

-- ── Table ─────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.AIInsights', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.AIInsights (
        InsightID        UNIQUEIDENTIFIER  NOT NULL DEFAULT NEWID(),
        Category         VARCHAR(50)       NOT NULL,
            -- 'Sales' | 'Customers' | 'Support' | 'Campaigns'
        Title            VARCHAR(200)      NOT NULL,
        Narrative        NVARCHAR(MAX)     NOT NULL,
            -- Human-readable executive prose from GPT-4o
        StructuredJson   NVARCHAR(MAX)     NOT NULL,
            -- Full structured JSON payload (key_findings, recommendations, etc.)
        MetricsJson      NVARCHAR(MAX)     NOT NULL,
            -- Raw metrics used as input to the generation prompt
        PeriodStart      DATE              NOT NULL,
        PeriodEnd        DATE              NOT NULL,
        GeneratedAt      DATETIME2(0)      NOT NULL DEFAULT GETUTCDATE(),
        ConfidenceScore  DECIMAL(4,3)      NULL
            CHECK (ConfidenceScore IS NULL OR (ConfidenceScore >= 0 AND ConfidenceScore <= 1)),
        ModelVersion     VARCHAR(50)       NOT NULL DEFAULT 'gpt-4o',
        PromptTokens     INT               NULL,
        CompletionTokens INT               NULL,

        CONSTRAINT PK_AIInsights PRIMARY KEY (InsightID),
        CONSTRAINT CK_AIInsights_Category CHECK (
            Category IN ('Sales', 'Customers', 'Support', 'Campaigns')
        )
    );

    PRINT 'Created table dbo.AIInsights';
END
ELSE
BEGIN
    PRINT 'Table dbo.AIInsights already exists — skipped.';
END
GO

-- ── Indexes ───────────────────────────────────────────────────────────────────

-- Most common query pattern: latest insight per category
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_AIInsights_Category_GeneratedAt'
      AND object_id = OBJECT_ID('dbo.AIInsights')
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_AIInsights_Category_GeneratedAt
        ON dbo.AIInsights (Category ASC, GeneratedAt DESC);
    PRINT 'Created index IX_AIInsights_Category_GeneratedAt';
END
GO

-- Period-range lookups (e.g. "insights for Q3 2025")
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_AIInsights_Period'
      AND object_id = OBJECT_ID('dbo.AIInsights')
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_AIInsights_Period
        ON dbo.AIInsights (PeriodStart ASC, PeriodEnd ASC);
    PRINT 'Created index IX_AIInsights_Period';
END
GO

PRINT 'Phase 7 schema (07_insights.sql) applied successfully.';
GO
