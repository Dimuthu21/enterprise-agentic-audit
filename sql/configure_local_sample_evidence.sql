-- Optional local-demo setup for the existing sample rows shown in this project.
-- Run after migrate_v2.sql against AuditDB. It does not delete any data.
-- It gives PO-1001 the verified fields needed for a matching-invoice demo.

UPDATE PurchaseOrders
SET Currency = 'USD',
    PurchaseCategory = 'Hardware'
WHERE PO_Number = 'PO-1001';

UPDATE PurchaseOrders
SET Currency = 'USD',
    PurchaseCategory = 'Supplies'
WHERE PO_Number = 'PO-1002';

-- The software PO keeps a verified SOW reference for policy demonstrations.
UPDATE PurchaseOrders
SET Currency = 'USD',
    PurchaseCategory = 'Software',
    SOWVerified = 1,
    SOWReference = 'LOCAL-DEMO-SOW-1003'
WHERE PO_Number = 'PO-1003';
