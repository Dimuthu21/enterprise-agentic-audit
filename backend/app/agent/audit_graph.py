import os
import re
import sqlite3
from typing import Dict, Any
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from backend.app.agent.state import AuditAgentState
from mcp_servers.erpserver import (
    get_purchase_order, 
    get_vendor_status, 
    record_audit_log,
    POQueryInput, 
    VendorQueryInput,
    AuditLogInput
)
from mcp_servers.policy_rag_server import search_procurement_policies, PolicyQueryInput
from mcp_servers.web_risk_server import check_vendor_web_risk, WebRiskInput

load_dotenv()

# -------------------------------------------------------------------
# Node 1: Ingest & Extract
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
# Node 2: Query ERP via FastMCP Tool
# -------------------------------------------------------------------
def query_erp_mcp_node(state: AuditAgentState) -> Dict[str, Any]:
    logs = state["logs"]
    po_number = state["po_number"]
    logs.append(f"Node [ERP_MCP]: Attempting SQL Server tool call for PO '{po_number}'...")

    if not po_number or po_number == "PO-UNKNOWN":
        tool_err = "Invalid or missing PO_Number format."
        logs.append(f"Node [ERP_MCP]: Tool Parameter Validation Error -> {tool_err}")
        return {"tool_error": tool_err, "logs": logs}

    po_res = get_purchase_order(POQueryInput(po_number=po_number))
    logs.append(f"Node [ERP_MCP]: DB Response -> {po_res}")

    if "Error:" in po_res or "not found" in po_res:
        tool_err = f"Database query failed: {po_res}"
        logs.append(f"Node [ERP_MCP]: Tool Execution Error -> {tool_err}")
        return {"tool_error": tool_err, "logs": logs}

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
        "tool_error": None,
        "logs": logs
    }

# -------------------------------------------------------------------
# Node 3: Reflection & Self-Correction Node
# -------------------------------------------------------------------
def reflect_and_retry_node(state: AuditAgentState) -> Dict[str, Any]:
    logs = state["logs"]
    retry_count = state["retry_count"] + 1
    tool_err = state.get("tool_error", "Unknown error")
    
    logs.append(f"Node [Reflection]: Analyzing error '{tool_err}' (Retry Attempt {retry_count}/{state['max_retries']})...")
    
    raw_text = state["invoice_raw_text"]
    fixed_po = state["po_number"]
    
    digit_match = re.search(r"PO[:\s#]*(\d+)", raw_text, re.IGNORECASE)
    if digit_match:
        fixed_po = f"PO-{digit_match.group(1)}"
        logs.append(f"Node [Reflection]: Reformulated PO string to '{fixed_po}'")

    return {
        "po_number": fixed_po,
        "retry_count": retry_count,
        "reflection_notes": f"Reflected on error: {tool_err}. Reformulated PO to {fixed_po}.",
        "logs": logs
    }

# -------------------------------------------------------------------
# Node 4: Query Compliance RAG & Web Risk MCP
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
    logs.append("Node [Auto_Approve]: Invoice matches PO budget. Preparing clean audit record...")
    return {
        "audit_status": "AUTO_APPROVED",
        "risk_level": "LOW",
        "discrepancy_reason": "Invoice matches PO approved amount. No risk detected.",
        "logs": logs
    }

# -------------------------------------------------------------------
# Node 6: Database Write Node (PROTECTED BY HUMAN-IN-THE-LOOP INTERRUPT)
# -------------------------------------------------------------------
def execute_db_write_node(state: AuditAgentState) -> Dict[str, Any]:
    logs = state["logs"]
    logs.append(f"Node [DB_Write]: Executing FastMCP write for Invoice '{state['invoice_id']}'...")

    final_status = state.get("audit_status", "PENDING_HUMAN_APPROVAL")
    if state.get("human_approved") is True:
        final_status = "MANUALLY_APPROVED"
    elif state.get("human_approved") is False:
        final_status = "REJECTED"

    # Write record directly to local SQL Server via FastMCP
    write_res = record_audit_log(AuditLogInput(
        invoice_id=state["invoice_id"],
        po_number=state["po_number"],
        billed_amount=state["billed_amount"],
        discrepancy_amount=state.get("discrepancy_amount", 0.0),
        status=final_status,
        reason=state.get("discrepancy_reason", "No reason provided")
    ))
    
    logs.append(f"Node [DB_Write]: SQL Server Result -> {write_res}")
    return {
        "audit_status": final_status,
        "logs": logs
    }

# -------------------------------------------------------------------
# Node 7: Fallback Exhausted Node
# -------------------------------------------------------------------
def retry_exhausted_node(state: AuditAgentState) -> Dict[str, Any]:
    logs = state["logs"]
    logs.append("Node [Exhausted]: Maximum retries exceeded. Routing to manual review queue...")
    return {
        "audit_status": "FAILED_RETRY_EXHAUSTED",
        "risk_level": "HIGH",
        "discrepancy_reason": f"System failed to resolve tool error after {state['max_retries']} retries.",
        "logs": logs
    }

# -------------------------------------------------------------------
# Conditional Router Logic
# -------------------------------------------------------------------
def evaluate_erp_outcome(state: AuditAgentState) -> str:
    if state.get("tool_error"):
        if state.get("retry_count", 0) < state.get("max_retries", 3):
            return "reflect_and_retry"
        return "retry_exhausted"
    
    if state["is_discrepancy_detected"]:
        return "query_compliance_risk"
    return "auto_approve"

# -------------------------------------------------------------------
# Build Graph with SQLite Checkpointer & HITL Interrupt Boundary
# -------------------------------------------------------------------
DB_CHECKPOINT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "checkpoints.sqlite")
os.makedirs(os.path.dirname(DB_CHECKPOINT_PATH), exist_ok=True)

# Initialize SQLite Connection for Checkpointers
conn = sqlite3.connect(DB_CHECKPOINT_PATH, check_same_thread=False)
checkpointer = SqliteSaver(conn)

def build_graph():
    workflow = StateGraph(AuditAgentState)

    workflow.add_node("extract_invoice", extract_invoice_node)
    workflow.add_node("query_erp_mcp", query_erp_mcp_node)
    workflow.add_node("reflect_and_retry", reflect_and_retry_node)
    workflow.add_node("query_compliance_risk", query_compliance_risk_node)
    workflow.add_node("auto_approve", auto_approve_node)
    workflow.add_node("execute_db_write", execute_db_write_node)
    workflow.add_node("retry_exhausted", retry_exhausted_node)

    workflow.set_entry_point("extract_invoice")
    workflow.add_edge("extract_invoice", "query_erp_mcp")

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

    workflow.add_edge("reflect_and_retry", "query_erp_mcp")
    workflow.add_edge("query_compliance_risk", "execute_db_write")
    workflow.add_edge("auto_approve", "execute_db_write")
    workflow.add_edge("execute_db_write", END)
    workflow.add_edge("retry_exhausted", END)

    # CRITICAL: Interrupt BEFORE running execute_db_write to enforce HITL
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["execute_db_write"]
    )

audit_app = build_graph()