import streamlit as st
import requests
import json
import pandas as pd
import sseclient

API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Enterprise Agentic Invoice Audit Dashboard",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Enterprise Agentic Audit Engine")
st.markdown("Automated Autonomous Audit with Human-in-the-Loop (HITL) Approval & Real-Time SSE Event Streaming")

# Sidebar - System Status & Health Check
st.sidebar.header("System Connections")
try:
    health_res = requests.get(f"{API_BASE_URL}/", timeout=2)
    if health_res.status_code == 200:
        st.sidebar.success("FastAPI Backend: ONLINE")
    else:
        st.sidebar.error("FastAPI Backend: DEGRADED")
except Exception:
    st.sidebar.error("FastAPI Backend: OFFLINE (Start Uvicorn server)")

st.sidebar.markdown("---")
st.sidebar.subheader("SQL Server Target")
st.sidebar.code("Server: LAPTOP-3THD09KC\nDatabase: AuditDB", language="text")

# Main Interface Tabs
tab1, tab2, tab3 = st.tabs(["🚀 Run Invoice Audit Stream", "⚖️ Pending HITL Approvals", "📊 SQL Audit Database Logs"])

# -------------------------------------------------------------------
# Tab 1: Live Invoice Processing & SSE Event Stream
# -------------------------------------------------------------------
with tab1:
    st.subheader("Process New Invoice Stream")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("**Input Invoice Text / OCR Output**")
        default_invoice = """INVOICE ID: INV-9950
PO NUMBER: PO-1001
Vendor: Acme IT Solutions
Total Amount Billed: $1850.00
Description: Enterprise server upgrades, rack installation, and software licenses."""
        
        invoice_input = st.text_area("Raw Invoice Payload", value=default_invoice, height=220)
        run_button = st.button("Submit to Agentic Audit Pipeline", type="primary")

    with col2:
        st.markdown("**Real-Time SSE Execution Logs**")
        log_container = st.container(border=True, height=300)
        
        if run_button:
            log_container.write("Initializing stream connection to backend...")
            
            try:
                response = requests.post(
                    f"{API_BASE_URL}/api/audit/stream",
                    json={"invoice_text": invoice_input},
                    stream=True,
                    timeout=30
                )
                
                client = sseclient.SSEClient(response)
                for event in client.events():
                    if event.data:
                        data = json.loads(event.data)
                        event_type = data.get("event")
                        
                        if event_type == "started":
                            log_container.info(f"🟢 **Started**: Thread ID `{data.get('thread_id')}` initialized.")
                        elif event_type == "node_update":
                            log_container.write(f"⚙️ **[{data.get('node')}]**: {data.get('log')}")
                        elif event_type == "awaiting_human_approval":
                            log_container.warning(f"⚠️ **HITL HALT**: Invoice flagged for discrepancy (${data.get('discrepancy_amount')}). Requires manual approval in Tab 2! Thread ID: `{data.get('thread_id')}`")
                            st.session_state["last_flagged_thread"] = data.get("thread_id")
                        elif event_type == "completed":
                            log_container.success(f"✅ **Execution Complete**: Audit finished with status `{data.get('status')}`.")
            except Exception as e:
                log_container.error(f"Stream error: {str(e)}")

# -------------------------------------------------------------------
# Tab 2: Human-in-the-Loop (HITL) Manual Review
# -------------------------------------------------------------------
with tab2:
    st.subheader("Human-in-the-Loop Compliance Review")
    
    target_thread = st.text_input(
        "Enter Flagged Thread ID to Resolve",
        value=st.session_state.get("last_flagged_thread", "")
    )
    
    reviewer_notes = st.text_area("Compliance Reviewer Notes", value="Approved after manual verification of vendor scope change.")
    
    col_app, col_rej = st.columns(2)
    
    with col_app:
        if st.button("✅ Approve Discrepancy", type="primary"):
            if target_thread:
                res = requests.post(
                    f"{API_BASE_URL}/api/audit/approve",
                    json={"thread_id": target_thread, "approved": True, "notes": reviewer_notes}
                )
                if res.status_code == 200:
                    st.success(f"Invoice approved and committed to database! Details: {res.json()}")
                else:
                    st.error(f"Approval failed: {res.text}")
            else:
                st.warning("Please provide a valid Thread ID.")
                
    with col_rej:
        if st.button("❌ Reject Invoice"):
            if target_thread:
                res = requests.post(
                    f"{API_BASE_URL}/api/audit/approve",
                    json={"thread_id": target_thread, "approved": False, "notes": reviewer_notes}
                )
                if res.status_code == 200:
                    st.error(f"Invoice rejected! Details: {res.json()}")
                else:
                    st.error(f"Rejection failed: {res.text}")
            else:
                st.warning("Please provide a valid Thread ID.")

# -------------------------------------------------------------------
# Tab 3: Historical Audit Database Logs
# -------------------------------------------------------------------
with tab3:
    st.subheader("SQL Server Live Audit Records")
    
    if st.button("🔄 Refresh Database Records"):
        try:
            logs_res = requests.get(f"{API_BASE_URL}/api/audit/logs")
            if logs_res.status_code == 200:
                logs_data = logs_res.json().get("data", [])
                if logs_data:
                    df = pd.DataFrame(logs_data)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No logs found in SQL Server database.")
            else:
                st.error(f"Failed to query backend: {logs_res.text}")
        except Exception as e:
            st.error(f"Error fetching logs: {str(e)}")