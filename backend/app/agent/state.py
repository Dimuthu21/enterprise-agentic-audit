from typing import TypedDict, Optional, List, Dict, Any

class AuditAgentState(TypedDict):
    """
    The central state schema passed between all nodes in the LangGraph execution graph.
    """
    # Raw Input
    invoice_raw_text: str
    
    # Extracted Invoice Fields
    invoice_id: Optional[str]
    po_number: Optional[str]
    vendor_id: Optional[str]
    vendor_name: Optional[str]
    billed_amount: Optional[float]
    
    # MCP Tool Retrieval Results
    po_db_data: Optional[str]
    vendor_db_data: Optional[str]
    policy_rag_data: Optional[str]
    web_risk_data: Optional[str]
    
    # Calculated Discrepancies & Risk Flags
    discrepancy_amount: float
    is_discrepancy_detected: bool
    risk_level: str  # 'LOW', 'MEDIUM', 'HIGH'
    
    # Workflow Execution Control
    next_node: str
    audit_status: str  # 'IN_PROGRESS', 'PENDING_HUMAN_APPROVAL', 'APPROVED', 'REJECTED'
    discrepancy_reason: str
    human_approved: Optional[bool]
    
    # Execution Step Trace Logs
    logs: List[str]