import sys
import os

# Add root directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.app.agent.audit_graph import audit_app

def test_graph_execution():
    print("==================================================")
    print("TEST CASE 1: Invoice with Price Discrepancy ($300 Over)")
    print("==================================================")
    
    sample_discrepancy_text = """
    INVOICE ID: INV-9042
    PO NUMBER: PO-1001
    Vendor: Acme IT Solutions
    Total Amount Billed: $1500.00
    Description: 10 Laptops with extended warranty
    """

    initial_state_1 = {
        "invoice_raw_text": sample_discrepancy_text,
        "logs": []
    }

    result_1 = audit_app.invoke(initial_state_1)

    for log in result_1["logs"]:
        print(log)

    print(f"\nFINAL AUDIT STATUS: {result_1['audit_status']}")
    print(f"RISK LEVEL: {result_1['risk_level']}")
    print(f"DISCREPANCY REASON: {result_1['discrepancy_reason']}")

    print("\n==================================================")
    print("TEST CASE 2: Matching Invoice (No Discrepancy)")
    print("==================================================")

    sample_matching_text = """
    INVOICE ID: INV-9043
    PO NUMBER: PO-1001
    Vendor: Acme IT Solutions
    Total Amount Billed: $1200.00
    Description: 10 Laptops
    """

    initial_state_2 = {
        "invoice_raw_text": sample_matching_text,
        "logs": []
    }

    result_2 = audit_app.invoke(initial_state_2)

    for log in result_2["logs"]:
        print(log)

    print(f"\nFINAL AUDIT STATUS: {result_2['audit_status']}")
    print(f"RISK LEVEL: {result_2['risk_level']}")

if __name__ == "__main__":
    test_graph_execution()