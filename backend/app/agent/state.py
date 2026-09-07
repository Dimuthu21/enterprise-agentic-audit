from typing import TypedDict

class AuditAgentState(TypedDict, total=False):
    thread_id: str
    invoice_raw_text: str
    invoice: dict
    facts: dict
    trace: list[dict]
    controls: dict
    explanation: dict
    review: dict
    audit_status: str
    intended_status: str
    error: str
    record: dict
    execution: dict
    created_at: str
