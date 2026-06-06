-- =============================================================================
-- InsightHub — Application Users Table
-- File        : database/schema/06_app_users.sql
-- Run order   : 6 of 6 (run after 05_views.sql)
-- Description : Creates dbo.AppUsers for InsightHub FastAPI authentication.
--               Stores bcrypt-hashed passwords — plain passwords are NEVER
--               stored or logged anywhere in the system.
--
-- RBAC roles
-- ──────────
--   Admin   — full access including insight generation trigger
--   Analyst — read all metrics, search, insights, embed reports
--   Viewer  — dashboard and Power BI reports only
--
-- Password seeding
-- ─────────────────
-- Run database/seed_users.py AFTER this migration to insert demo users
-- with properly bcrypt-hashed passwords.
-- =============================================================================

SET NOCOUNT ON;
PRINT '── InsightHub: creating AppUsers table ──';

IF OBJECT_ID('dbo.AppUsers', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.AppUsers
    (
        UserID          INT             NOT NULL    IDENTITY(1,1),
        Username        NVARCHAR(100)   NOT NULL,
        Email           NVARCHAR(254)   NOT NULL,
        -- bcrypt hash of the password — never the plain password
        PasswordHash    NVARCHAR(255)   NOT NULL,
        Role            VARCHAR(20)     NOT NULL    CONSTRAINT DF_AppUsers_Role    DEFAULT 'Viewer',
        IsActive        BIT             NOT NULL    CONSTRAINT DF_AppUsers_Active  DEFAULT 1,
        CreatedDate     DATETIME2(0)    NOT NULL    CONSTRAINT DF_AppUsers_Created DEFAULT SYSUTCDATETIME(),
        LastLoginDate   DATETIME2(0)    NULL,

        CONSTRAINT PK_AppUsers          PRIMARY KEY CLUSTERED (UserID),
        CONSTRAINT UQ_AppUsers_Username UNIQUE (Username),
        CONSTRAINT UQ_AppUsers_Email    UNIQUE (Email),
        CONSTRAINT CK_AppUsers_Role     CHECK (Role IN ('Admin', 'Analyst', 'Viewer'))
    );
    PRINT '  ✓ AppUsers table created';
END
ELSE
    PRINT '  – AppUsers already exists, skipped';
GO

-- Non-clustered index on Username for fast login lookups
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_AppUsers_Username')
    CREATE NONCLUSTERED INDEX IX_AppUsers_Username
        ON dbo.AppUsers (Username)
        INCLUDE (PasswordHash, Role, IsActive);
GO

-- Record in migration history
IF OBJECT_ID('dbo.SchemaVersion', 'U') IS NOT NULL
AND NOT EXISTS (SELECT 1 FROM dbo.SchemaVersion WHERE MigrationName = '006_app_users')
BEGIN
    INSERT INTO dbo.SchemaVersion (MigrationName, Description)
    VALUES ('006_app_users', 'AppUsers table for FastAPI JWT authentication with RBAC roles');
    PRINT '  ✓ Migration 006_app_users recorded';
END
GO

PRINT '── AppUsers migration complete ──';
PRINT 'Next step: run python database/seed_users.py to create demo users.';
