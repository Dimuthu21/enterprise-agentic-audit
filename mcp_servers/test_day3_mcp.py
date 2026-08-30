from policy_rag_server import search_procurement_policies, PolicyQueryInput
from web_risk_server import check_vendor_web_risk, WebRiskInput

def test_day3_tools():
    print("--- 1. Testing Policy RAG MCP Server ---")
    policy_res = search_procurement_policies(SqlQueryInput if False else PolicyQueryInput(
        query="What happens if invoice amount is greater than approved PO amount?"
    ))
    print(policy_res)

    print("\n--- 2. Testing Web Risk MCP Server (Clear Vendor) ---")
    clear_vendor_res = check_vendor_web_risk(WebRiskInput(vendor_name="Acme IT Solutions"))
    print(clear_vendor_res)

    print("\n--- 3. Testing Web Risk MCP Server (Flagged Vendor) ---")
    risk_vendor_res = check_vendor_web_risk(WebRiskInput(vendor_name="Shadow Tech Logistics"))
    print(risk_vendor_res)

if __name__ == "__main__":
    test_day3_tools()