import sys
import os
import pyodbc

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.app.agent.audit_graph import audit_app

def test_hitl_workflow():
    print("==================================================================")
    print("STEP 1: Run Agent Initial Pass (Halts at Human Approval Gate)")
    print("==================================================================")

    invoice_text = """
    INVOICE ID: INV-7711
    PO NUMBER: PO-1001
    Vendor: Acme IT Solutions
    Total Amount Billed: $1650.00
    Description: 10 Laptops with custom software bundle
    """

    # Thread config identifies this persistent session in SQLite
    thread_config = {"configurable": {"thread_id": "session_thread_7711"}}

    initial_state = {
        "invoice_raw_text": invoice_text,
        "logs": [],
        "retry_count": 0,
        "max_retries": 3
    }

    # First Pass: Agent executes until it reaches 'execute_db_write' and HALTS
    for step in audit_app.stream(initial_state, thread_config):
        node_name = list(step.keys())[0]
        print(f"Executed Node: [{node_name}]")

    # Check state at interrupt point
    current_state = audit_app.get_state(thread_config)
    print(f"\n--- EXECUTION HALTED ---")
    print(f"Next Node Pending Execution: {current_state.next}")
    print(f"Current Status: {current_state.values.get('audit_status')}")
    print(f"Discrepancy: ${current_state.values.get('discrepancy_amount'):.2f}")

    print("\n==================================================================")
    print("STEP 2: Human Reviews Alert in UI & Clicks 'Approve Adjustment'")
    print("==================================================================")

    # Human provides approval input by updating graph state
    audit_app.update_state(
        thread_config,
        {"human_approved": True, "audit_status": "MANUALLY_APPROVED"}
    )

    # Resume graph execution passing None to continue from checkpoint
    for step in audit_app.stream(None, thread_config):
        node_name = list(step.keys())[0]
        print(f"Resumed & Executed Node: [{node_name}]")

    final_state = audit_app.get_state(thread_config)
    print(f"\nFINAL STATUS AFTER RESUME: {final_state.values.get('audit_status')}")

    # Verify write directly in local SQL Server
    print("\n--- STEP 3: Verifying Direct SQL Server Write ---")
    conn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=LAPTOP-3THD09KC;DATABASE=AuditDB;Trusted_Connection=yes;")
    cursor = conn.cursor()
    cursor.execute("SELECT TOP 1 InvoiceID, PO_Number, BilledAmount, Status FROM AuditLogs WHERE InvoiceID = 'INV-7711' ORDER BY AuditID DESC;")
    row = cursor.fetchone()
    conn.close()

    if row:
        print(f"SQL Server Verified Record: Invoice '{row.InvoiceID}' | Status: '{row.Status}' | Billed: ${row.BilledAmount:.2f}")
    else:
        print("Error: Record not found in SQL Server.")

if __name__ == "__main__":
    test_hitl_workflow()