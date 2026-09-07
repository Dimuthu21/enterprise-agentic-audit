"""SQL Server remains the live ERP; SQLite is an explicitly initialized demo store."""
import json
import sqlite3
from decimal import Decimal
from contextlib import contextmanager, closing
from pathlib import Path
from backend.app.config import Settings

@contextmanager
def connection(settings=None):
    s = settings or Settings()
    if s.db_mode == 'demo':
        if not Path(s.demo_db).exists(): raise RuntimeError('Initialize demo database first')
        conn = sqlite3.connect(s.demo_db, timeout=15)
    elif s.db_mode == 'sqlserver':
        import pyodbc
        if not s.db_connection: raise RuntimeError('DB_CONNECTION_STRING required')
        conn = pyodbc.connect(s.db_connection, timeout=10)
        conn.timeout = 15
    else: raise ValueError('Unsupported DB_MODE')
    try:
        yield conn
    finally:
        conn.close()

def get_po(po_number):
    with connection() as conn:
        cur=conn.cursor()
        if Settings().db_mode == 'sqlserver':
            columns={row[0].casefold() for row in cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='PurchaseOrders'").fetchall()}
            optional=lambda name, fallback: name if name.casefold() in columns else fallback
            query=("SELECT PO_Number,VendorID,ApprovedAmount,ItemDescription,Status,"
                   f"{optional('Currency', 'NULL')},{optional('PurchaseCategory', 'NULL')},"
                   f"{optional('SOWVerified', 'NULL')},{optional('SOWReference', 'NULL')} "
                   "FROM PurchaseOrders WHERE PO_Number=?")
        else:
            query='SELECT PO_Number,VendorID,ApprovedAmount,ItemDescription,Status,Currency,PurchaseCategory,SOWVerified,SOWReference FROM PurchaseOrders WHERE PO_Number=?'
        row = cur.execute(query, (po_number,)).fetchone()
        if not row: return None
        return dict(zip(['po_number','vendor_id','approved_amount','description','status','currency','category','sow_verified','sow_reference'],
            [row[0],row[1],str(row[2]),row[3],row[4],row[5],row[6],bool(row[7]) if row[7] is not None else None,row[8]]))

def get_vendor(vendor_id):
    with connection() as conn:
        row = conn.cursor().execute('SELECT VendorID,VendorName,RiskStatus,ApprovedCategory FROM Vendors WHERE VendorID=?', (vendor_id,)).fetchone()
        return dict(zip(['vendor_id','vendor_name','risk_status','category'],row)) if row else None

def _legacy_reason(record):
    """Short, operator-readable summary for the existing SQL Server AuditLogs table."""
    summary=record.get('explanation',{}).get('summary') or 'Deterministic invoice audit completed.'
    findings=', '.join(record.get('controls',{}).get('findings',[])) or 'no findings'
    return f"{summary[:300]} Findings: {findings[:100]} [audit-thread:{record['thread_id']}]"[:500]

def _write_sqlserver_legacy_log(cur, record):
    """Keep the established AuditLogs table useful for existing local dashboards."""
    marker=f"[audit-thread:{record['thread_id']}]"
    existing=cur.execute('SELECT AuditID FROM AuditLogs WHERE DiscrepancyReason LIKE ?', (f'%{marker}%',)).fetchone()
    if existing:
        return
    invoice=record['invoice']; controls=record['controls']
    discrepancy=controls.get('discrepancy_amount')
    cur.execute(
        'INSERT INTO AuditLogs (InvoiceID, PO_Number, BilledAmount, DiscrepancyAmount, Status, DiscrepancyReason) VALUES (?, ?, ?, ?, ?, ?)',
        (invoice['invoice_id'], invoice['po_number'], str(invoice['billed_amount']), str(discrepancy or '0.00'), record['status'], _legacy_reason(record))
    )

def write_record(record):
    """Write a final result once, then confirm it is visible in the configured audit store."""
    payload = json.dumps(record, sort_keys=True, separators=(',',':'), default=str)
    with connection() as conn:
        cur = conn.cursor()
        if Settings().db_mode == 'sqlserver':
            # The full record table is added by the supplied additive migration. The
            # existing AuditLogs table is still written for compatibility.
            table=cur.execute("SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='AuditRecords'").fetchone()
            if table:
                row=cur.execute('SELECT Payload FROM AuditRecords WHERE ThreadID=?', (record['thread_id'],)).fetchone()
                if row and row[0] != payload:
                    raise RuntimeError('Persistence idempotency conflict')
                if not row:
                    cur.execute('INSERT INTO AuditRecords (ThreadID,Payload) VALUES (?,?)', (record['thread_id'],payload))
            _write_sqlserver_legacy_log(cur, record)
            conn.commit()
            marker=f"[audit-thread:{record['thread_id']}]"
            if not cur.execute('SELECT AuditID FROM AuditLogs WHERE DiscrepancyReason LIKE ?', (f'%{marker}%',)).fetchone():
                raise RuntimeError('AuditLogs persistence not confirmed')
        else:
            try:
                cur.execute('INSERT INTO AuditRecords (ThreadID,Payload) VALUES (?,?)', (record['thread_id'],payload))
                conn.commit()
            except Exception:
                conn.rollback()
                row = cur.execute('SELECT Payload FROM AuditRecords WHERE ThreadID=?', (record['thread_id'],)).fetchone()
                if not row or row[0] != payload: raise RuntimeError('Persistence failed or idempotency conflict') from None
            row = cur.execute('SELECT Payload FROM AuditRecords WHERE ThreadID=?', (record['thread_id'],)).fetchone()
            if not row or row[0] != payload: raise RuntimeError('Persistence not confirmed')
    return {'persisted':True, 'thread_id':record['thread_id']}

def logs():
    with connection() as conn:
        cur=conn.cursor()
        if Settings().db_mode == 'sqlserver':
            rows=cur.execute('SELECT TOP 20 AuditID, InvoiceID, PO_Number, BilledAmount, DiscrepancyAmount, Status, DiscrepancyReason, CreatedAt FROM AuditLogs ORDER BY AuditID DESC').fetchall()
            return [dict(zip(('audit_id','invoice_id','po_number','billed_amount','discrepancy_amount','status','reason','created_at'),
                (row[0],row[1],row[2],str(row[3]),str(row[4]),row[5],row[6],str(row[7])))) for row in rows]
        rows=cur.execute('SELECT Payload FROM AuditRecords ORDER BY CreatedAt DESC LIMIT 20').fetchall()
        return [json.loads(r[0]) for r in rows]

def initialize_demo(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS Vendors(VendorID TEXT PRIMARY KEY, VendorName TEXT, RiskStatus TEXT, ApprovedCategory TEXT);
        CREATE TABLE IF NOT EXISTS PurchaseOrders(PO_Number TEXT PRIMARY KEY, VendorID TEXT, ApprovedAmount TEXT, ItemDescription TEXT, Status TEXT, Currency TEXT, PurchaseCategory TEXT, SOWVerified INTEGER, SOWReference TEXT);
        CREATE TABLE IF NOT EXISTS AuditRecords(ThreadID TEXT PRIMARY KEY, Payload TEXT NOT NULL, CreatedAt TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')
        conn.executemany('INSERT OR IGNORE INTO Vendors VALUES (?,?,?,?)', [('VEND-001','Acme IT Solutions','CLEAR','Hardware'),('VEND-002','Global Office Supplies','CLEAR','Supplies'),('VEND-003','Shadow Tech Logistics','FLAGGED','Software')])
        conn.executemany('INSERT OR IGNORE INTO PurchaseOrders VALUES (?,?,?,?,?,?,?,?,?)', [('PO-1001','VEND-001','1200.00','10 Laptops','OPEN','USD','Hardware',None,None),('PO-1002','VEND-002','450.00','5 Chairs','OPEN','USD','Supplies',None,None),('PO-1003','VEND-003','3000.00','Software maintenance','OPEN','USD','Software',None,None)])
        conn.commit()

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--init-demo', required=True)
    initialize_demo(p.parse_args().init_demo)
