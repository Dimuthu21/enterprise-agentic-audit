from pydantic import BaseModel, Field
from typing import Optional, List, Any

class InvoiceAuditRequest(BaseModel):
    invoice_text: str = Field(..., description="Raw invoice text extracted via OCR or manual input.")
    thread_id: Optional[str] = Field(None, description="Unique thread ID for tracking state persistence.")

class HumanApprovalRequest(BaseModel):
    thread_id: str = Field(..., description="Thread ID of the halted execution stream.")
    approved: bool = Field(..., description="True to approve invoice discrepancy, False to reject.")
    notes: Optional[str] = Field(None, description="Optional notes provided by the compliance reviewer.")

class AuditLogResponse(BaseModel):
    audit_id: int
    invoice_id: str
    po_number: str
    billed_amount: float
    discrepancy_amount: float
    status: str
    reason: str
    created_at: str