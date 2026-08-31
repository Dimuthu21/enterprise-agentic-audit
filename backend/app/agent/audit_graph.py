import os
import re
from typing import Dict, Any
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from backend.app.agent.state import AuditAgentState
from mcp_servers.erpserver import get_purchase_order, get_vendor_status, POQueryInput, VendorQueryInput
from mcp_servers.policy_rag_server import search_procurement_policies, PolicyQueryInput
from mcp_servers.web_risk_server import check_vendor_web_risk, WebRiskInput

load_dotenv()

# -------------------------------------------------------------------
# Node 1: Ingest & Extract Invoice Information
# -------------------------------------------------------------------
def extract_invoice_node(state: AuditAgentState) -> Dict[str, Any]:
    text = state["invoice_raw_text"]
    logs = state.get("logs", [])
    logs.append("Node [Extract]: Processing raw invoice text...")

    inv_id_match = re.search(r"INV-\d+", text)
    po_match = re.search(r"PO-\d+", text)
    amount_match = re.search(r"\$(\d+(?:\.\d{2})?)", text)
    vendor_match = re.search(r"Vendor:\s*([A-Za-z0-9\s]+)", text)

    invoice_id = inv_id_match.group(0) if inv_id_match else "INV-UNKNOWN"
    po_number = po_match.group(0) if po_match else "PO-UNKNOWN"
    billed_amount = float(amount_match.group(1)) if amount_match else 0.0
    vendor_name = vendor_match.group(1).strip() if vendor_match else "Unknown Vendor"

    logs.append(f"Node [Extract]: Extracted Invoice ID '{invoice_id}', PO '{po_number}', Amount '${billed_amount:.2f}'")
    
    return {
        "invoice_id": invoice_id,
        "po_number": po_number,
        "billed_amount": billed_amount,
        "vendor_name": vendor_name,
        "retry_count": state.get("retry_count", 0),
        "max_retries": 3,
        "logs": logs
    }

# -------------------------------------------------------------------
# Node 2: Query ERP SQL Server via FastMCP Tool with Error Checking
# -------------------------------------------------------------------
def query_erp_mcp_node(state: AuditAgentState) -> Dict[str, Any]:
    logs = state["logs"]
    po_number = state["po_number"]
    logs.append(f"Node [ERP_MCP]: Attempting SQL Server tool call for PO '{po_number}'...")

    # Validate PO parameter before execution
    if not po_number or po_number == "PO-UNKNOWN":
        tool_err = "Invalid or missing PO_Number format."
        logs.append(f"Node [ERP_MCP]: Tool Parameter Validation Error -> {tool_err}")
        return {
            "tool_error": tool_err,
            "logs": logs
        }

    # Execute FastMCP PO Tool Call
    po_res = get_purchase_order(POQueryInput(po_number=po_number))
    logs.append(f"Node [ERP_MCP]: DB Response -> {po_res}")

    if "Error:" in po_res or "not found" in po_res:
        tool_err = f"Database query failed: {po_res}"
        logs.append(f"Node [ERP_MCP]: Tool Execution Error -> {tool_err}")
        return {
            "tool_error": tool_err,
            "logs": logs
        }

    # Extract vendor ID and check vendor status
    vendor_id = "VEND-001"
    if "VendorID: " in po_res:
        vendor_id = po_res.split("VendorID: ")[1].split(" |")[0].strip()

    vendor_res = get_vendor_status(VendorQueryInput(vendor_id=vendor_id))
    logs.append(f"Node [ERP_MCP]: Vendor Response -> {vendor_res}")

    approved_amount = 0.0
    if "Approved Amount: $" in po_res:
        approved_amount = float(po_res.split("Approved Amount: $")[1].split(" |")[0])

    discrepancy = state["billed_amount"] - approved_amount
    is_discrepancy = discrepancy > 0.01

    return {
        "vendor_id": vendor_id,
        "po_db_data": po_res,
        "vendor_db_data": vendor_res,
        "discrepancy_amount": discrepancy,
        "is_discrepancy_detected": is_discrepancy,
        "tool_error": None,  # Clear any prior errors on success
        "logs": logs
    }

# -------------------------------------------------------------------
# Node 3: Reflection & Self-Correction Node (CYCLIC EDGE TARGET)
# -------------------------------------------------------------------
def reflect_and_retry_node(state: AuditAgentState) -> Dict[str, Any]:
    logs = state["logs"]
    retry_count = state["retry_count"] + 1
    tool_err = state.get("tool_error", "Unknown error")
    
    logs.append(f"Node [Reflection]: Analyzing error '{tool_err}' (Retry Attempt {retry_count}/{state['max_retries']})...")
    
    # Heuristic/Reflection logic: Attempt to fix common PO string formatting issues
    raw_text = state["invoice_raw_text"]
    fixed_po = state["po_number"]
    
    # Retry strategy: Search for potential digits if standard prefix failed
    digit_match = re.search(r"PO[:\s#]*(\d+)", raw_text, re.IGNORECASE)
    if digit_match:
        fixed_po = f"PO-{digit_match.group(1)}"
        logs.append(f"Node [Reflection]: Self-correction applied. Reformulated PO string to '{fixed_po}'")
    else:
        logs.append("Node [Reflection]: Unable to infer fixed PO from text context.")

    return {
        "po_number": fixed_po,
        "retry_count": retry_count,
        "reflection_notes": f"Reflected on error: {tool_err}. Reformulated PO to {fixed_po}.",
        "logs": logs
    }

# -------------------------------------------------------------------
# Node 4: Query Policy RAG & Web Risk MCP Tools
# -------------------------------------------------------------------
def query_compliance_risk_node(state: AuditAgentState) -> Dict[str, Any]:
    logs = state["logs"]
    logs.append("Node [Risk_Audit]: Executing Policy RAG & Web Risk MCP checks...")

    policy_res = search_procurement_policies(SqlQueryInput if False else PolicyQueryInput(
        query=f"What is the tolerance rule for an invoice exceeding PO budget by ${state['discrepancy_amount']:.2f}?"
    ))
    logs.append(f"Node [Risk_Audit]: RAG Policy -> {policy_res}")

    web_res = check_vendor_web_risk(WebRiskInput(vendor_name=state["vendor_name"]))
    logs.append(f"Node [Risk_Audit]: Web Search Risk -> {web_res}")

    risk_level = "HIGH" if ("FLAGGED" in state.get("vendor_db_data", "") or "Risk Alert" in web_res or state["discrepancy_amount"] > 100.0) else "MEDIUM"

    return {
        "policy_rag_data": policy_res,
        "web_risk_data": web_res,
        "risk_level": risk_level,
        "audit_status": "PENDING_HUMAN_APPROVAL",
        "discrepancy_reason": f"Discrepancy of ${state['discrepancy_amount']:.2f} detected. Web Risk Level: {risk_level}.",
        "logs": logs
    }

# -------------------------------------------------------------------
# Node 5: Auto Approve Node
# -------------------------------------------------------------------
def auto_approve_node(state: AuditAgentState) -> Dict[str, Any]:
    logs = state["logs"]
    logs.append("Node [Auto_Approve]: Invoice matches PO budget exactly. Auto-approving record...")
    return {
        "audit_status": "APPROVED",
        "risk_level": "LOW",
        "discrepancy_reason": "Invoice matches PO approved amount. No risk detected.",
        "logs": logs
    }

# -------------------------------------------------------------------
# Node 6: Fallback Exhausted Node
# -------------------------------------------------------------------
def retry_exhausted_node(state: AuditAgentState) -> Dict[str, Any]:
    logs = state["logs"]
    logs.append("Node [Exhausted]: Maximum retries exceeded. Routing to manual review queue...")
    return {
        "audit_status": "FAILED_RETRY_EXHAUSTED",
        "risk_level": "HIGH",
        "discrepancy_reason": f"System failed to resolve tool error after {state['max_retries']} retries. Last error: {state.get('tool_error')}",
        "logs": logs
    }

# -------------------------------------------------------------------
# Conditional Router 1: ERP Query Result Evaluation
# -------------------------------------------------------------------
def evaluate_erp_outcome(state: AuditAgentState) -> str:
    # If error occurred, route to reflection OR exhausted fallback
    if state.get("tool_error"):
        if state.get("retry_count", 0) < state.get("max_retries", 3):
            return "reflect_and_retry"
        return "retry_exhausted"
    
    # If successful, check discrepancy
    if state["is_discrepancy_detected"]:
        return "query_compliance_risk"
    return "auto_approve"

# -------------------------------------------------------------------
# Build and Compile the Graph State Machine
# -------------------------------------------------------------------
def build_graph():
    workflow = StateGraph(AuditAgentState)

    # Register All Nodes
    workflow.add_node("extract_invoice", extract_invoice_node)
    workflow.add_node("query_erp_mcp", query_erp_mcp_node)
    workflow.add_node("reflect_and_retry", reflect_and_retry_node)
    workflow.add_node("query_compliance_risk", query_compliance_risk_node)
    workflow.add_node("auto_approve", auto_approve_node)
    workflow.add_node("retry_exhausted", retry_exhausted_node)

    # Set Entry Point
    workflow.set_entry_point("extract_invoice")
    workflow.add_edge("extract_invoice", "query_erp_mcp")

    # Conditional Routing from ERP Query Node
    workflow.add_conditional_edges(
        "query_erp_mcp",
        evaluate_erp_outcome,
        {
            "reflect_and_retry": "reflect_and_retry",
            "retry_exhausted": "retry_exhausted",
            "query_compliance_risk": "query_compliance_risk",
            "auto_approve": "auto_approve"
        }
    )

    # CYCLIC EDGE: Reflection node loops BACK into query_erp_mcp to retry!
    workflow.add_edge("reflect_and_retry", "query_erp_mcp")

    # Final Edges
    workflow.add_edge("query_compliance_risk", END)
    workflow.add_edge("auto_approve", END)
    workflow.add_edge("retry_exhausted", END)

    return workflow.compile()

audit_app = build_graph()