"""Application-owned stdio subprocess; stdout is reserved for MCP protocol."""
import hmac
import os
from mcp.server.fastmcp import FastMCP
from backend.app.config import Settings
from backend.app.contracts import ToolResult
from backend.app import storage, web_risk
from backend.app.policies import documents, VERSION

mcp = FastMCP('Invoice Audit Evidence')

def result(fn):
    try:
        data=fn()
        return ToolResult(success=data is not None, data=data or {}, error=None if data is not None else 'not_found')
    except Exception:
        return ToolResult(success=False, error='tool_unavailable')

@mcp.tool()
def get_purchase_order(po_number: str) -> ToolResult:
    """Retrieve authoritative purchase order and independently stored SOW evidence."""
    return result(lambda: storage.get_po(po_number))

@mcp.tool()
def get_vendor_status(vendor_id: str) -> ToolResult:
    """Retrieve authoritative vendor identity and risk status."""
    return result(lambda: storage.get_vendor(vendor_id))

@mcp.tool()
def search_procurement_policies(query: str) -> ToolResult:
    """Retrieve the active policy set; all four controls are mandatory for invoice audits."""
    def search():
        mode=Settings().policy_mode
        if mode == 'demo': return {'policies':documents(), 'retrieval':'demo_canonical', 'version':VERSION}
        if mode != 'chroma': raise ValueError('Invalid policy mode')
        from backend.app.policy_index import search
        return search(query)
    return result(search)

@mcp.tool()
def check_vendor_web_risk(vendor_name: str) -> ToolResult:
    """Search public risk evidence, reporting provider mode, identity uncertainty and sources."""
    return result(lambda: web_risk.check(vendor_name, Settings().web_mode))

@mcp.tool()
def record_audit_log(record: dict, capability: str) -> ToolResult:
    """Application-only write, never exposed to Gemini."""
    expected=os.getenv('AUDIT_WRITE_CAPABILITY','')
    if not expected or not hmac.compare_digest(expected,capability):
        return ToolResult(success=False,error='unauthorized')
    if record.get('status') not in ('AUTO_APPROVED','MANUALLY_APPROVED','REJECTED'):
        return ToolResult(success=False,error='invalid_status')
    return result(lambda: storage.write_record(record))

def main():
    # Import/load ML libraries before entering the protocol event loop. Some
    # transformer backends initialize their own thread/runtime state on import.
    if Settings().policy_mode == 'chroma':
        from backend.app import policy_index
        policy_index._index = policy_index.index()
    mcp.run(transport='stdio')

if __name__ == '__main__': main()
