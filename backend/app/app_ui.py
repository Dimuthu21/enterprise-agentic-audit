"""A clear operator-facing Streamlit interface for the invoice audit workflow."""
import json
import os

import pandas as pd
import requests
import sseclient
import streamlit as st

from backend.app.ui_events import apply_event

st.set_page_config(page_title="Invoice Audit Console", page_icon="✓", layout="wide")
st.markdown("""<style>
.stApp { background:#f6f8fc; color:#172033; }.block-container {max-width:1280px;padding-top:2.2rem}
.hero {background:linear-gradient(120deg,#172554,#2563eb);color:white;padding:2rem 2.2rem;border-radius:18px;margin-bottom:1.4rem;box-shadow:0 12px 30px rgba(30,64,175,.18)}
.hero h1 {margin:0;font-size:2.25rem}.hero p {margin:.4rem 0 0;opacity:.88}.panel {background:white;border:1px solid #e4e8f1;border-radius:14px;padding:1.25rem;min-height:180px}
.stage {border-left:4px solid #16a34a;background:#f8fafc;border-radius:8px;padding:.62rem .85rem;margin:.5rem 0}.small {color:#64748b;font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;font-weight:700}.thread {font-family:monospace;font-size:.8rem;word-break:break-all;color:#334155}
</style>""", unsafe_allow_html=True)

BASE=os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
STAGES={
    "extract":"Read invoice with Gemini", "evidence":"Verify purchase order, vendor, policies, and web evidence",
    "select_tools":"Collect optional read-only evidence", "decide":"Apply deterministic policy controls",
    "review":"Wait for authorized reviewer", "persist":"Save final decision to audit database",
}
if "audit" not in st.session_state:
    st.session_state.audit={"logs":[],"pending":False,"result":None,"thread_id":None}
audit=st.session_state.audit

def headers():
    return {"Authorization":"Bearer "+st.session_state.get("token", "")}

def health():
    try:
        response=requests.get(BASE+"/",timeout=3); response.raise_for_status()
        return response.json(),None
    except requests.RequestException:
        return None,"Backend is offline. Start the backend CMD window, then refresh this page."

def status_text(result):
    return (result or {}).get("status","READY").replace("_"," ").title()

def show_result():
    result=audit.get("result") or {}; status=result.get("status","READY")
    icon="🟢" if status in ("AUTO_APPROVED","MANUALLY_APPROVED","REJECTED") else "🟠" if status=="AWAITING_REVIEW" else "🔴" if status in ("VALIDATION_FAILED","PERSISTENCE_FAILED","ERROR") else "🔵"
    st.markdown('<div class="small">Current audit status</div>',unsafe_allow_html=True)
    st.subheader(f"{icon} {status_text(result)}")
    if audit.get("thread_id"):
        st.markdown('<div class="small">Saved thread ID</div>',unsafe_allow_html=True)
        st.markdown(f'<div class="thread">{audit["thread_id"]}</div>',unsafe_allow_html=True)
    if result.get("error"): st.error(result["error"])
    if result.get("explanation"):
        st.markdown("**Decision summary**")
        st.write(result["explanation"].get("summary","No summary available."))
    controls=result.get("controls") or {}
    if controls.get("classification"):
        first,second,third=st.columns(3)
        first.metric("Invoice class",controls["classification"].replace("_"," ").title())
        second.metric("Difference",f"USD {controls.get('discrepancy_amount','—')}")
        third.metric("Difference %",f"{controls.get('discrepancy_percent','—')}%")
    if controls.get("findings"):
        st.markdown("**Items requiring attention**")
        for finding in controls["findings"]: st.write("• "+finding.replace("_"," ").title())

def show_timeline():
    st.markdown('<div class="small">Audit timeline</div>',unsafe_allow_html=True)
    if not audit.get("logs"):
        st.info("Start an audit to see each verification stage here.")
        return
    for log in audit["logs"]:
        stage=log.replace(" finished","")
        st.markdown(f'<div class="stage"><strong>✓ {STAGES.get(stage,log)}</strong><br><span style="color:#64748b">Completed</span></div>',unsafe_allow_html=True)

def run_audit(invoice_text, timeline_slot, result_slot):
    audit.clear(); audit.update(logs=[],pending=False,result=None,thread_id=None)
    try:
        with requests.post(BASE+"/api/audit/stream",json={"invoice_text":invoice_text},headers=headers(),stream=True,timeout=(10,180)) as response:
            response.raise_for_status()
            for event in sseclient.SSEClient(response).events():
                if event.data:
                    apply_event(audit,json.loads(event.data))
                    with timeline_slot.container(): show_timeline()
                    with result_slot.container(): show_result()
        if not audit.get("result"):
            apply_event(audit,{"event":"error","error":"The stream ended before the audit returned a final state."})
    except requests.RequestException:
        apply_event(audit,{"event":"error","error":"Could not reach the backend. Confirm both CMD windows are running and your local token is valid."})

def audit_rows(records):
    rows=[]
    for item in records:
        if "invoice_id" in item: rows.append(item)
        else:
            invoice=item.get("invoice",{}); controls=item.get("controls",{})
            rows.append({"invoice_id":invoice.get("invoice_id"),"po_number":invoice.get("po_number"),"billed_amount":invoice.get("billed_amount"),"discrepancy_amount":controls.get("discrepancy_amount"),"status":item.get("status"),"created_at":item.get("created_at"),"reason":item.get("explanation",{}).get("summary","")})
    return rows

with st.sidebar:
    st.header("Local access")
    st.session_state.token=st.text_input("Reviewer access token",type="password",help="Paste the local-reviewer token from .env. This is not the Gemini API key.")
    st.caption("The backend decides reviewer identity. Keep your Gemini key only in `.env`.")
    st.divider(); st.markdown("**Demo checklist**")
    for item in ("Paste reviewer token","Start audit","Review the evidence","Approve or reject","View saved records"): st.write("• "+item)
    if st.button("Clear this screen"):
        st.session_state.audit={"logs":[],"pending":False,"result":None,"thread_id":None}; st.rerun()

info,offline=health()
st.markdown('<div class="hero"><h1>Invoice Audit Console</h1><p>Evidence-led invoice review with controlled approval and verified audit records.</p></div>',unsafe_allow_html=True)
if offline: st.error(offline)
elif info:
    st.caption(f"Database: {info['db_mode'].upper()}  ·  Policy source: {info['policy_mode'].upper()}  ·  Web-risk: {info['web_mode'].upper()}")
    if any(info[key]=="demo" for key in ("db_mode","policy_mode","web_mode")):
        st.info("Demo mode is active. Live web evidence is intentionally unavailable, so reviewer approval will be required.")

left,right=st.columns([1.35,1])
with left:
    st.markdown('<div class="panel">',unsafe_allow_html=True); st.subheader("1. Submit an invoice")
    st.caption("Include invoice ID, PO number, vendor, explicit USD, and one total amount.")
    invoice_text=st.text_area("Invoice text",height=210,label_visibility="collapsed",value="""INVOICE ID: INV-LOCAL-1001
PO NUMBER: PO-1001
Vendor: Acme IT Solutions
Total Amount Billed: USD $1,200.00
Description: 10 Laptops""")
    start=st.button("Start audit",type="primary",use_container_width=True,disabled=not bool(st.session_state.get("token")))
    st.markdown("</div>",unsafe_allow_html=True)
with right:
    st.markdown('<div class="panel">',unsafe_allow_html=True); result_slot=st.empty()
    with result_slot.container(): show_result()
    st.markdown("</div>",unsafe_allow_html=True)

st.write(""); st.markdown('<div class="panel">',unsafe_allow_html=True)
timeline_slot=st.empty()
with timeline_slot.container(): show_timeline()
st.markdown("</div>",unsafe_allow_html=True)
if start:
    run_audit(invoice_text,timeline_slot,result_slot); st.rerun()

result=audit.get("result") or {}
if audit.get("pending"):
    st.divider(); st.subheader("2. Reviewer decision required")
    controls=result.get("controls") or {}; blocked=controls.get("blocked",[])
    if blocked: st.error("This audit cannot be approved because required evidence is missing: "+", ".join(x.replace("_"," ") for x in blocked)+".")
    else: st.warning("Review is required. In demo mode, this is expected because live web-risk evidence is intentionally unavailable.")
    notes=st.text_area("Reviewer notes",placeholder="State why you approve or reject this invoice.")
    approve,reject=st.columns(2)
    approved=approve.button("Approve and save record",type="primary",use_container_width=True,disabled=bool(blocked) or not notes.strip())
    rejected=reject.button("Reject and save record",use_container_width=True,disabled=not notes.strip())
    if approved or rejected:
        try:
            response=requests.post(BASE+"/api/audit/approve",headers=headers(),json={"thread_id":audit["thread_id"],"approved":approved,"notes":notes},timeout=180)
            if response.ok:
                apply_event(audit,response.json()); st.success("Decision saved and database persistence confirmed."); st.rerun()
            else: st.error(response.json().get("detail","Could not save reviewer decision."))
        except requests.RequestException: st.error("The response was unavailable. Load the saved thread before retrying.")

st.divider()
with st.expander("Saved audit tools"):
    st.caption("Use these after an audit starts. They are for recovery and proof of persisted records.")
    thread=st.text_input("Saved thread ID",value=audit.get("thread_id") or "")
    load,retry,records=st.columns(3)
    if load.button("Load saved audit",use_container_width=True,disabled=not thread):
        try:
            response=requests.get(BASE+"/api/audit/"+thread,headers=headers(),timeout=15); response.raise_for_status()
            apply_event(audit,response.json()); st.rerun()
        except requests.RequestException: st.error("Saved audit was not found or the token is invalid.")
    if retry.button("Retry saved execution",use_container_width=True,disabled=not thread):
        try:
            response=requests.post(BASE+"/api/audit/"+thread+"/retry",headers=headers(),timeout=180)
            if response.ok: apply_event(audit,response.json()); st.rerun()
            else: st.error(response.json().get("detail","Retry was not available for this audit."))
        except requests.RequestException: st.error("Retry request could not reach the backend.")
    if records.button("Load persisted audit records",use_container_width=True):
        try:
            response=requests.get(BASE+"/api/audit/logs",headers=headers(),timeout=20); response.raise_for_status()
            rows=audit_rows(response.json().get("data",[]))
            if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
            else: st.info("No completed audit records are stored yet.")
        except requests.RequestException: st.error("Audit database could not be reached.")
