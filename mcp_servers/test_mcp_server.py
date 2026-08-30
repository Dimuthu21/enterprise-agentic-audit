from erpserver import get_purchase_order, get_vendor_status, record_audit_log, POQueryInput, VendorQueryInput, AuditLogInput

def run_local_tests():
    print("--- 1. Testing PO Query MCP Tool ---")
    po_result = get_purchase_order(POQueryInput(po_number="PO-1001"))
    print(po_result)

    print("\n--- 2. Testing Vendor Status MCP Tool ---")
    vendor_result = get_vendor_status(VendorQueryInput(vendor_id="VEND-001"))
    print(vendor_result)

    print("\n--- 3. Testing Audit Log Write MCP Tool ---")
    log_result = record_audit_log(AuditLogInput(
        invoice_id="INV-TEST-01",
        po_number="PO-1001",
        billed_amount=1500.00,
        discrepancy_amount=300.00,
        status="FLAGGED_FOR_HUMAN",
        reason="Billed amount exceeded approved PO amount by $300.00"
    ))
    print(log_result)

if __name__ == "__main__":
    run_local_tests()