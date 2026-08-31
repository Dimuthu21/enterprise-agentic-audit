import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.app.agent.audit_graph import audit_app

def test_self_correction_cycle():
    print("==================================================================")
    print("TEST CASE: Malformed PO Format (Triggers Cycle -> Reflection -> Retry)")
    print("==================================================================")

    # Invoice text with tricky PO formatting ("PO # 1001" instead of "PO-1001")
    malformed_invoice_text = """
    INVOICE ID: INV-9988
    Reference PO # 1001
    Vendor: Acme IT Solutions
    Total Amount Billed: $1500.00
    Description: 10 Laptops with extended support
    """

    initial_state = {
        "invoice_raw_text": malformed_invoice_text,
        "logs": [],
        "retry_count": 0,
        "max_retries": 3
    }

    result = audit_app.invoke(initial_state)

    print("\n--- EXECUTION TRACE LOGS ---")
    for log in result["logs"]:
        print(log)

    print(f"\nFINAL STATUS: {result['audit_status']}")
    print(f"RETRY ATTEMPTS TAKEN: {result['retry_count']}")
    print(f"FINAL PO RESOLVED: {result['po_number']}")
    print(f"DISCREPANCY REASON: {result['discrepancy_reason']}")

if __name__ == "__main__":
    test_self_correction_cycle()