-- Create Database
CREATE DATABASE AuditDB;
GO

USE AuditDB;
GO

-- 1. Vendors Table
CREATE TABLE Vendors (
    VendorID VARCHAR(50) PRIMARY KEY,
    VendorName VARCHAR(100) NOT NULL,
    RiskStatus VARCHAR(20) DEFAULT 'CLEAR',
    ApprovedCategory VARCHAR(50) NOT NULL
);

-- 2. PurchaseOrders Table
CREATE TABLE PurchaseOrders (
    PO_Number VARCHAR(50) PRIMARY KEY,
    VendorID VARCHAR(50) FOREIGN KEY REFERENCES Vendors(VendorID),
    ApprovedAmount DECIMAL(18, 2) NOT NULL,
    ItemDescription VARCHAR(255) NOT NULL,
    Status VARCHAR(20) DEFAULT 'OPEN'
);

-- 3. AuditLogs Table
CREATE TABLE AuditLogs (
    AuditID INT IDENTITY(1,1) PRIMARY KEY,
    InvoiceID VARCHAR(50) NOT NULL,
    PO_Number VARCHAR(50) FOREIGN KEY REFERENCES PurchaseOrders(PO_Number),
    BilledAmount DECIMAL(18, 2) NOT NULL,
    DiscrepancyAmount DECIMAL(18, 2) DEFAULT 0.00,
    Status VARCHAR(30) NOT NULL,
    DiscrepancyReason VARCHAR(500),
    CreatedAt DATETIME DEFAULT GETDATE()
);

-- Insert Sample Enterprise Data
INSERT INTO Vendors
    (VendorID, VendorName, RiskStatus, ApprovedCategory)
VALUES
    ('VEND-001', 'Acme IT Solutions', 'CLEAR', 'Hardware'),
    ('VEND-002', 'Global Office Supplies', 'CLEAR', 'Supplies'),
    ('VEND-003', 'Shadow Tech Logistics', 'FLAGGED', 'Services');

INSERT INTO PurchaseOrders
    (PO_Number, VendorID, ApprovedAmount, ItemDescription, Status)
VALUES
    ('PO-1001', 'VEND-001', 1200.00, '10 Laptops', 'OPEN'),
    ('PO-1002', 'VEND-002', 450.00, '5 Ergonomic Chairs', 'OPEN'),
    ('PO-1003', 'VEND-003', 3000.00, 'Custom Software Maintenance', 'OPEN');