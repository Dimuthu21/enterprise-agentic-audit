from pydantic import Field, StrictBool
from backend.app.contracts import StrictModel

class InvoiceAuditRequest(StrictModel):
    invoice_text: str = Field(min_length=1,max_length=50000)
    thread_id: str | None = Field(default=None,pattern=r'^[A-Za-z0-9_-]{1,100}$')

class HumanApprovalRequest(StrictModel):
    thread_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    approved: StrictBool
    notes: str = Field(min_length=1,max_length=2000)
