import os
import json
import asyncio
import pyodbc
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from backend.app.schemas import InvoiceAuditRequest, HumanApprovalRequest
from backend.app.agent.audit_graph import audit_app

app = FastAPI(
    title="Enterprise Agentic Audit API",
    description="FastAPI backend providing SSE streaming and HITL controls for autonomous invoice auditing.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_CONN_STR = "DRIVER={ODBC Driver 17 for SQL Server};SERVER=LAPTOP-3THD09KC;DATABASE=AuditDB;Trusted_Connection=yes;"

@app.get("/")
def read_root():
    return {"status": "Online", "system": "Enterprise Agentic Audit Engine"}

@app.post("/api/audit/stream")
async def stream_invoice_audit(request: InvoiceAuditRequest):
    thread_id = request.thread_id or f"thread_{os.urandom(4).hex()}"
    thread_config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "invoice_raw_text": request.invoice_text,
        "logs": [],
        "retry_count": 0,
        "max_retries": 3
    }

    async def event_generator() -> AsyncGenerator[str, None]:
        yield json.dumps({
            "event": "started",
            "thread_id": thread_id,
            "message": "Graph execution initialized."
        })

        # Stream graph nodes execution safely
        for step in audit_app.stream(initial_state, thread_config, stream_mode="updates"):
            # Handle tuple/dict format variations from LangGraph checkpointer
            if isinstance(step, tuple):
                node_name, node_output = step[0], step[1]
            elif isinstance(step, dict):
                node_name = list(step.keys())[0]
                node_output = step[node_name]
            else:
                continue

            if not isinstance(node_output, dict):
                continue

            latest_logs = node_output.get("logs", [])
            last_log = latest_logs[-1] if latest_logs else f"Node [{node_name}] executed."

            payload = {
                "event": "node_update",
                "node": str(node_name),
                "thread_id": thread_id,
                "log": str(last_log).replace("\n", " "),  # Sanitize newlines for SSE format
                "status": node_output.get("audit_status", "IN_PROGRESS")
            }
            yield json.dumps(payload)
            await asyncio.sleep(0.2)

        current_state = audit_app.get_state(thread_config)
        
        if current_state.next and "execute_db_write" in current_state.next:
            yield json.dumps({
                "event": "awaiting_human_approval",
                "thread_id": thread_id,
                "status": "PENDING_HUMAN_APPROVAL",
                "discrepancy_amount": current_state.values.get("discrepancy_amount", 0.0),
                "discrepancy_reason": current_state.values.get("discrepancy_reason", ""),
                "risk_level": current_state.values.get("risk_level", "MEDIUM")
            })
        else:
            yield json.dumps({
                "event": "completed",
                "thread_id": thread_id,
                "status": current_state.values.get("audit_status", "COMPLETED")
            })

    return EventSourceResponse(event_generator())

@app.post("/api/audit/approve")
async def submit_human_approval(request: HumanApprovalRequest):
    thread_config = {"configurable": {"thread_id": request.thread_id}}
    
    current_state = audit_app.get_state(thread_config)
    if not current_state.values:
        raise HTTPException(status_code=404, detail=f"Thread '{request.thread_id}' not found.")

    new_status = "MANUALLY_APPROVED" if request.approved else "REJECTED"
    
    audit_app.update_state(
        thread_config,
        {
            "human_approved": request.approved,
            "audit_status": new_status,
            "discrepancy_reason": current_state.values.get("discrepancy_reason", "") + (f" | Reviewer Note: {request.notes}" if request.notes else "")
        }
    )

    for step in audit_app.stream(None, thread_config):
        pass

    final_state = audit_app.get_state(thread_config)
    return {
        "thread_id": request.thread_id,
        "final_status": final_state.values.get("audit_status"),
        "message": "Human decision recorded and applied to database record."
    }

@app.get("/api/audit/logs")
def get_audit_logs():
    try:
        conn = pyodbc.connect(DB_CONN_STR)
        cursor = conn.cursor()
        
        # Execute SELECT query for top records
        cursor.execute("SELECT TOP 20 * FROM AuditLogs ORDER BY AuditID DESC;")
        
        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            # Convert values to strings/floats to ensure JSON serializability
            row_dict = {}
            for col, val in zip(columns, row):
                row_dict[col] = str(val) if val is not None else ""
            results.append(row_dict)
            
        conn.close()
        return {"count": len(results), "data": results}
    except Exception as e:
        print(f"[SQL ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)