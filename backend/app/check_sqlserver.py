"""Safe local SQL Server diagnostic; reads configuration/schema but never writes."""
from backend.app.config import Settings
from backend.app.storage import connection


def main():
    settings=Settings()
    if settings.db_mode != 'sqlserver':
        print('SQL Server check skipped: DB_MODE is not sqlserver')
        return 1
    with connection() as db:
        cur=db.cursor()
        row=cur.execute('SELECT COUNT(*) FROM AuditLogs').fetchone()
        columns=[item[0] for item in cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='PurchaseOrders' ORDER BY ORDINAL_POSITION").fetchall()]
        has_audit_records=bool(cur.execute("SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='AuditRecords'").fetchone())
        po=cur.execute("SELECT PO_Number, Currency, PurchaseCategory FROM PurchaseOrders WHERE PO_Number='PO-1001'").fetchone()
    print('SQL Server connection: OK')
    print('Existing AuditLogs rows:', row[0])
    print('AuditRecords table:', 'present' if has_audit_records else 'not present')
    print('PO-1001 evidence:', tuple(po) if po else 'not found')
    required={'Currency','PurchaseCategory','SOWVerified','SOWReference'}
    missing=required-set(columns)
    if missing:
        print('Migration required; missing columns:', ', '.join(sorted(missing)))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
