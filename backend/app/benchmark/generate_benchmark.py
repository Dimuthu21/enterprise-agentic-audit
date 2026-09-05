import json
import os

def generate_synthetic_dataset():
    dataset = []

    # Category 1: Standard Valid Invoices (15 samples)
    for i in range(1, 16):
        dataset.append({
            "id": f"TEST-{i:03d}",
            "category": "VALID",
            "invoice_text": f"INVOICE ID: INV-200{i}\nPO NUMBER: PO-1001\nVendor: Acme IT Solutions\nTotal Amount Billed: $1200.00\nDescription: Standard hardware supplies and routine maintenance.",
            "expected_outputs": {
                "po_number": "PO-1001",
                "vendor_name": "Acme IT Solutions",
                "billed_amount": 1200.0,
                "expected_status": "APPROVED",
                "requires_human_approval": False,
                "expected_discrepancy": 0.0
            }
        })

    # Category 2: Pricing Discrepancies (15 samples)
    for i in range(16, 31):
        billed = 1750.0 + (i * 10)
        discrepancy = billed - 1200.0
        dataset.append({
            "id": f"TEST-{i:03d}",
            "category": "PRICING_DISCREPANCY",
            "invoice_text": f"INVOICE ID: INV-300{i}\nPO NUMBER: PO-1001\nVendor: Acme IT Solutions\nTotal Amount Billed: ${billed:.2f}\nDescription: Server upgrades and software licensing.",
            "expected_outputs": {
                "po_number": "PO-1001",
                "vendor_name": "Acme IT Solutions",
                "billed_amount": billed,
                "expected_status": "PENDING_HUMAN_APPROVAL",
                "requires_human_approval": True,
                "expected_discrepancy": discrepancy
            }
        })

    # Category 3: High-Risk / Blacklisted Vendors (10 samples)
    for i in range(31, 41):
        dataset.append({
            "id": f"TEST-{i:03d}",
            "category": "HIGH_RISK_VENDOR",
            "invoice_text": f"INVOICE ID: INV-400{i}\nPO NUMBER: PO-9999\nVendor: Shell Corp Logistics\nTotal Amount Billed: $4500.00\nDescription: Expedited overseas shipping and handling.",
            "expected_outputs": {
                "po_number": "PO-9999",
                "vendor_name": "Shell Corp Logistics",
                "billed_amount": 4500.0,
                "expected_status": "REJECTED",
                "requires_human_approval": False,
                "expected_discrepancy": 4500.0
            }
        })

    # Category 4: Missing PO or Policy Violations (10 samples)
    for i in range(41, 51):
        dataset.append({
            "id": f"TEST-{i:03d}",
            "category": "POLICY_VIOLATION",
            "invoice_text": f"INVOICE ID: INV-500{i}\nPO NUMBER: UNKNOWN\nVendor: Global Consulting Group\nTotal Amount Billed: $8900.00\nDescription: Unapproved executive advisory services.",
            "expected_outputs": {
                "po_number": "UNKNOWN",
                "vendor_name": "Global Consulting Group",
                "billed_amount": 8900.0,
                "expected_status": "REJECTED",
                "requires_human_approval": False,
                "expected_discrepancy": 8900.0
            }
        })

    output_dir = os.path.dirname(__file__)
    file_path = os.path.join(output_dir, "audit_benchmark_50.json")

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=4)

    print(f"✅ Successfully generated {len(dataset)} synthetic audit benchmark cases.")
    print(f"📁 Dataset location: {file_path}")

if __name__ == "__main__":
    generate_synthetic_dataset()