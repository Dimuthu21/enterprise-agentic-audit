"""Read-only connectivity check. Uses the same environment configuration as MCP."""
from backend.app.storage import connection

def test_connection():
    with connection() as conn:
        count=conn.cursor().execute('SELECT COUNT(*) FROM PurchaseOrders').fetchone()[0]
        print(f'Connected; purchase order rows: {count}')

if __name__=='__main__': test_connection()
