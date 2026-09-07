-- Additive migration for existing AuditDB. Review and run manually; no automatic migration.
-- Existing purchase evidence is deliberately left NULL until verified by an ERP owner.
IF COL_LENGTH('PurchaseOrders','Currency') IS NULL
    ALTER TABLE PurchaseOrders ADD Currency VARCHAR(3) NULL;
IF COL_LENGTH('PurchaseOrders','PurchaseCategory') IS NULL
    ALTER TABLE PurchaseOrders ADD PurchaseCategory VARCHAR(50) NULL;
IF COL_LENGTH('PurchaseOrders','SOWVerified') IS NULL
    ALTER TABLE PurchaseOrders ADD SOWVerified BIT NULL;
IF COL_LENGTH('PurchaseOrders','SOWReference') IS NULL
    ALTER TABLE PurchaseOrders ADD SOWReference NVARCHAR(500) NULL;
IF OBJECT_ID('AuditRecords','U') IS NULL
    CREATE TABLE AuditRecords (
        ThreadID VARCHAR(100) NOT NULL PRIMARY KEY,
        Payload NVARCHAR(MAX) NOT NULL,
        CreatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_AuditRecords_Json CHECK (ISJSON(Payload)=1)
    );
-- AuditLogs is retained and remains the operator-facing compatibility log.
-- The application writes each confirmed final decision to AuditRecords and AuditLogs.
