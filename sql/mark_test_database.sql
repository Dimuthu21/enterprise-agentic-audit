-- Run ONLY in a disposable evaluation database. This marker permits opt-in live fixture inserts.
IF OBJECT_ID('AuditEnvironment','U') IS NULL
    CREATE TABLE AuditEnvironment(Environment VARCHAR(10) PRIMARY KEY CHECK(Environment='test'));
IF NOT EXISTS(SELECT 1 FROM AuditEnvironment WHERE Environment='test')
    INSERT INTO AuditEnvironment(Environment) VALUES ('test');
