import streamlit as st
import requests
import json
import pandas as pd
import sseclient

API_BASE_URL = "http://127.0.0.1:8000"
st.set_page_config(
    page_title="Enterprise Agentic Audit Dashboard",
    page_icon="🛡️",
    layout="wide"
)

# Initialize Session State Variables
if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = None
if "pending_approval" not in st.session_state:
    st.session_state["pending_approval"] = False
if "discrepancy_info" not in st.session_state:
    st.session_state["discrepancy_info"] = {}
if "execution_logs" not in st.session_state:
    st.session_state["execution_logs"] = []

st.title("🛡️ Enterprise Agentic Audit Engine")
st.markdown("Real-time Autonomous Audit Pipeline with Live SSE Event Streams & HITL Modal Intercepts")

# Sidebar - System Status & Health Check
st.sidebar.header("System Monitor")
try:
    health_res = requests.get(f"{API_BASE_URL}/", timeout=2)
    if health_res.status_code == 200:
        st.sidebar.success("FastAPI Backend: ONLINE")
    else:
        st.sidebar.warning("FastAPI Backend: DEGRADED")
except Exception:
    st.sidebar.error("FastAPI Backend: OFFLINE")

st.sidebar.markdown("---")
st.sidebar.subheader("Active Thread Context")
st.sidebar.info(f"Thread ID: `{st.session_state['thread_id'] or 'None'}`")

tab1, tab2 = st.tabs(["🚀 Live Invoice Audit Stream", "📊 SQL Audit Logs"])

# -------------------------------------------------------------------
# Tab 1: Live Invoice Audit & HITL Interactive Workflow
# -------------------------------------------------------------------
with tab1:
    col_input, col_stream = st.columns([1, 1])

    with col_input:
        st.subheader("Invoice Upload Zone")
        default_invoice = """INVOICE ID: INV-9988
PO NUMBER: PO-1001
Vendor: Acme IT Solutions
Total Amount Billed: $1950.00
Description: Emergency database cluster upgrade and licensing fees."""
        
        invoice_text = st.text_area("Raw Invoice Payload (OCR Input)", value=default_invoice, height=220)
        
        if st.button("Submit & Start Audit Stream", type="primary", use_container_width=True):
            st.session_state["execution_logs"] = []
            st.session_state["pending_approval"] = False
            st.session_state["thread_id"] = None
            
            try:
                response = requests.post(
                    f"{API_BASE_URL}/api/audit/stream",
                    json={"invoice_text": invoice_text},
                    stream=True,
                    timeout=30
                )
                
                client = sseclient.SSEClient(response)
                for event in client.events():
                    if event.data:
                        data = json.loads(event.data)
                        event_type = data.get("event")
                        
                        if event_type == "started":
                            st.session_state["thread_id"] = data.get("thread_id")
                            st.session_state["execution_logs"].append(f"🟢 Started session `{data.get('thread_id')}`")
                        elif event_type == "node_update":
                            st.session_state["execution_logs"].append(f"⚙️ [{data.get('node')}]: {data.get('log')}")
                        elif event_type == "awaiting_human_approval":
                            st.session_state["pending_approval"] = True
                            st.session_state["discrepancy_info"] = {
                                "amount": data.get("discrepancy_amount", 0.0),
                                "reason": data.get("discrepancy_reason", "N/A"),
                                "risk": data.get("risk_level", "MEDIUM")
                            }
                            st.session_state["execution_logs"].append("⚠️ Execution Halted: Human-in-the-Loop approval required.")
                        elif event_type == "completed":
                            st.session_state["execution_logs"].append(f"✅ Audit finalized: {data.get('status')}")
                            
            except Exception as e:
                st.session_state["execution_logs"].append(f"❌ Error: {str(e)}")

    with col_stream:
        st.subheader("Live Agent Trajectory Stream")
        log_box = st.container(border=True, height=350)
        for log in st.session_state["execution_logs"]:
            if "🟢" in log:
                log_box.info(log)
            elif "⚠️" in log:
                log_box.warning(log)
            elif "❌" in log:
                log_box.error(log)
            elif "✅" in log:
                log_box.success(log)
            else:
                log_box.text(log)

    # -------------------------------------------------------------------
    # Day 9 Modal: Human Approval Dialog Intercept
    # -------------------------------------------------------------------
    if st.session_state["pending_approval"]:
        @st.dialog("🚨 Human-in-the-Loop Risk Intercept Required")
        def show_approval_modal():
            info = st.session_state["discrepancy_info"]
            st.warning("The agent detected a billing discrepancy exceeding standard tolerance.")
            
            st.markdown(f"**Thread ID:** `{st.session_state['thread_id']}`")
            st.markdown(f"**Discrepancy Amount:** `${info.get('amount', 0.0):.2f}`")
            st.markdown(f"**Calculated Risk Level:** `{info.get('risk')}`")
            st.markdown(f"**Flagged Reason:** {info.get('reason')}")
            
            reviewer_notes = st.text_input("Reviewer Compliance Notes", value="Discrepancy verified and approved by Auditor.")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Approve Invoice", type="primary", use_container_width=True):
                    res = requests.post(
                        f"{API_BASE_URL}/api/audit/approve",
                        json={
                            "thread_id": st.session_state["thread_id"],
                            "approved": True,
                            "notes": reviewer_notes
                        }
                    )
                    if res.status_code == 200:
                        st.session_state["pending_approval"] = False
                        st.session_state["execution_logs"].append(f"✅ State Resumed & Approved: {res.json().get('final_status')}")
                        st.rerun()
                    else:
                        st.error("Failed to post approval decision.")
            
            with c2:
                if st.button("❌ Reject Invoice", use_container_width=True):
                    res = requests.post(
                        f"{API_BASE_URL}/api/audit/approve",
                        json={
                            "thread_id": st.session_state["thread_id"],
                            "approved": False,
                            "notes": reviewer_notes
                        }
                    )
                    if res.status_code == 200:
                        st.session_state["pending_approval"] = False
                        st.session_state["execution_logs"].append(f"❌ State Resumed & Rejected: {res.json().get('final_status')}")
                        st.rerun()
                    else:
                        st.error("Failed to post rejection decision.")

        show_approval_modal()

# -------------------------------------------------------------------
# Tab 2: Historical SQL Database Records
# -------------------------------------------------------------------
with tab2:
    st.subheader("SQL Server Live Audit Logs")
    if st.button("🔄 Refresh Database Audit Records"):
        try:
            res = requests.get(f"{API_BASE_URL}/api/audit/logs")
            if res.status_code == 200:
                data = res.json().get("data", [])
                if data:
                    df = pd.DataFrame(data)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No records found.")
        except Exception as e:
            st.error(f"Error fetching database logs: {str(e)}")