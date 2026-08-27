import pyodbc

CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=LAPTOP-3THD09KC;"
    "DATABASE=AuditDB;"
    "Trusted_Connection=yes;"
)

def test_connection():
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM PurchaseOrders;")
        row_count = cursor.fetchone()[0]

        print(f"Successfully connected! Found {row_count} Purchase Orders in local SQL Server.")

        conn.close()

    except Exception as e:
        print(f"Error connecting to local SQL Server: {e}")


if __name__ == "__main__":
    test_connection()