import os
import re
from typing import Dict, Any
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

# Import State Schema
from backend.app.agent.state import AuditAgentState

# Import Local MCP Tool Functions created on Day 2 & Day 3
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

    # Regex/Parser fallback for extracting key data fields deterministically
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
        "logs": logs
    }

# -------------------------------------------------------------------
# Node 2: Query ERP SQL Server via MCP Tool
# -------------------------------------------------------------------
def query_erp_mcp_node(state: AuditAgentState) -> Dict[str, Any]:
    logs = state["logs"]
    logs.append(f"Node [ERP_MCP]: Querying local SQL Server for PO '{state['po_number']}'...")

    # Call FastMCP PO Tool function directly
    po_res = get_purchase_order(POQueryInput(po_number=state["po_number"]))
    logs.append(f"Node [ERP_MCP]: DB Response -> {po_res}")

    # Extract vendor ID from PO result text if available
    vendor_id = "VEND-001"
    if "VendorID: " in po_res:
        vendor_id = po_res.split("VendorID: ")[1].split(" |")[0].strip()

    # Call FastMCP Vendor Tool function
    vendor_res = get_vendor_status(VendorQueryInput(vendor_id=vendor_id))
    logs.append(f"Node [ERP_MCP]: Vendor Response -> {vendor_res}")

    # Calculate discrepancy against SQL record
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
        "logs": logs
    }

# -------------------------------------------------------------------
# Node 3: Query Policy Vector Store (RAG) & Web Risk MCP Tools
# -------------------------------------------------------------------
def query_compliance_risk_node(state: AuditAgentState) -> Dict[str, Any]:
    logs = state["logs"]
    logs.append("Node [Risk_Audit]: Discrepancy detected! Executing Policy RAG & Web Risk MCP checks...")

    # Query RAG Policy tool
    policy_res = search_procurement_policies(SqlQueryInput if False else PolicyQueryInput(
        query=f"What is the tolerance rule for an invoice exceeding PO budget by ${state['discrepancy_amount']:.2f}?"
    ))
    logs.append(f"Node [Risk_Audit]: RAG Policy -> {policy_res}")

    # Query Web Risk tool
    web_res = check_vendor_web_risk(WebRiskInput(vendor_name=state["vendor_name"]))
    logs.append(f"Node [Risk_Audit]: Web Search Risk -> {web_res}")

    risk_level = "HIGH" if ("FLAGGED" in state.get("vendor_db_data", "") or "Risk Alert" in web_res or state["discrepancy_amount"] > 100.0) else "MEDIUM"

    return {
        "policy_rag_data": policy_res,
        "web_risk_data": web_res,
        "risk_level": risk_level,
        "audit_status": "PENDING_HUMAN_APPROVAL",
        "discrepancy_reason": f"Discrepancy of ${state['discrepancy_amount']:.2f} detected against approved PO limit. Web Risk Level: {risk_level}.",
        "logs": logs
    }

# -------------------------------------------------------------------
# Node 4: Auto Approve Node (No Discrepancy Found)
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
# Conditional Edge Router Function
# -------------------------------------------------------------------
def route_audit_path(state: AuditAgentState) -> str:
    if state["is_discrepancy_detected"]:
        return "query_compliance_risk"
    return "auto_approve"

# -------------------------------------------------------------------
# Build and Compile the LangGraph Instance
# -------------------------------------------------------------------
def build_graph():
    workflow = StateGraph(AuditAgentState)

    # Add Nodes
    workflow.add_node("extract_invoice", extract_invoice_node)
    workflow.add_node("query_erp_mcp", query_erp_mcp_node)
    workflow.add_node("query_compliance_risk", query_compliance_risk_node)
    workflow.add_node("auto_approve", auto_approve_node)

    # Add Edges
    workflow.set_entry_point("extract_invoice")
    workflow.add_edge("extract_invoice", "query_erp_mcp")

    # Add Conditional Edge from ERP Query
    workflow.add_conditional_edges(
        "query_erp_mcp",
        route_audit_path,
        {
            "query_compliance_risk": "query_compliance_risk",
            "auto_approve": "auto_approve"
        }
    )

    workflow.add_edge("query_compliance_risk", END)
    workflow.add_edge("auto_approve", END)

    return workflow.compile()

# Global compiled graph instance
audit_app = build_graph()