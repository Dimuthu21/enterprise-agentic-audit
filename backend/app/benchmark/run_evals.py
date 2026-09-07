"""Actual graph + HTTP API evaluation. Categories are read only after execution."""
import argparse
import asyncio
import copy
import importlib.metadata
import json
import os
import tempfile
import time
import uuid
from datetime import datetime,timezone
from pathlib import Path
import httpx
from backend.app.config import Settings
from backend.app.service import AuditService
from backend.app.main import create_app
from backend.app.benchmark.controlled import ControlledModel,ControlledGateway
from backend.app.policies import VERSION

async def evaluate(dataset,output,live=False,confirm_test_database=False):
    if live:
        if not confirm_test_database: raise ValueError('Live evaluation requires --confirm-test-database')
        settings=Settings()
        if settings.db_mode!='sqlserver' or settings.web_mode!='live' or settings.policy_mode!='chroma' or not settings.api_key:
            raise ValueError('Live evaluation requires Gemini, SQL Server, live web and Chroma configuration')
        from backend.app.storage import connection
        with connection() as conn:
            marker=conn.cursor().execute("SELECT Environment FROM AuditEnvironment WHERE Environment='test'").fetchone()
            if not marker: raise ValueError('Database is not marked as a disposable test database')
    token=uuid.uuid4().hex
    original_users=os.environ.get('AUDIT_USERS_JSON')
    os.environ['AUDIT_USERS_JSON']=json.dumps({'evaluation':{'token':token,'role':'reviewer'}})
    results=[]
    try:
        with tempfile.TemporaryDirectory(prefix='audit-evaluation-') as tmp:
            for original in dataset:
                case=copy.deepcopy(original)
                if live and ('fail' in case or 'web' in case or 'policies' in case):
                    results.append({'id':case['id'],'category':case['category'],'skipped':'Controlled fault injection is offline-only'})
                    continue
                if live:
                    # Insert only into an explicitly marked test database. Never mutate existing ERP rows.
                    number=str(uuid.uuid4().int)[:18]
                    po_number='PO-'+number; vendor_id='EVAL-'+number
                    old_po=case['model_response'].get('po_number')
                    case['invoice_text']=case['invoice_text'].replace('PO-1001',po_number)
                    if old_po=='PO-1001': case['model_response']['po_number']=po_number
                    if case['expected']['extraction']: case['expected']['extraction']['po_number']=po_number
                    po=case['po'];vendor=case['vendor']
                    with connection() as conn:
                        conn.cursor().execute('INSERT INTO Vendors(VendorID,VendorName,RiskStatus,ApprovedCategory) VALUES (?,?,?,?)',
                            (vendor_id,vendor['vendor_name'],vendor['risk_status'],po['category']))
                        conn.cursor().execute('INSERT INTO PurchaseOrders(PO_Number,VendorID,ApprovedAmount,ItemDescription,Status,Currency,PurchaseCategory,SOWVerified,SOWReference) VALUES (?,?,?,?,?,?,?,?,?)',
                            (po_number,vendor_id,po['approved_amount'],'Evaluation fixture','OPEN','USD',po['category'],po.get('sow_verified'),po.get('sow_reference')))
                        conn.commit()
                    settings.state_path=str(Path(tmp)/'live.sqlite')
                    svc=AuditService(settings)
                else:
                    model=ControlledModel(case['model_response'])
                    gateway=ControlledGateway(po=case['po'],vendor=case['vendor'],policies=case.get('policies'),web=case.get('web'),fail=case.get('fail'))
                    svc=AuditService(Settings(state_path=str(Path(tmp)/'offline.sqlite'),model='controlled-offline'),lambda s:model,lambda s:gateway)
                start=time.perf_counter()
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(svc)),base_url='http://evaluation') as client:
                    response=await client.post('/api/audit/stream',headers={'Authorization':'Bearer '+token},json={'invoice_text':case['invoice_text']})
                    response.raise_for_status()
                    events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
                    last=events[-1]
                    state=(await svc.state(last['thread_id'])).values
                    review_resume=None
                    if last['event']=='awaiting_human_approval':
                        decision={'thread_id':last['thread_id'],'approved':False,'notes':'Evaluation rejection of review-required test invoice'}
                        reviewed=await client.post('/api/audit/approve',headers={'Authorization':'Bearer '+token},json=decision)
                        duplicate=await client.post('/api/audit/approve',headers={'Authorization':'Bearer '+token},json=decision)
                        review_resume=reviewed.status_code==200 and reviewed.json().get('status')=='REJECTED' and duplicate.status_code==409
                latency=time.perf_counter()-start
                expected=case['expected']; inv=state.get('invoice'); controls=state.get('controls',{})
                extraction_correct=inv is None if expected['extraction'] is None else inv is not None and all(inv.get(k)==v for k,v in expected['extraction'].items())
                failures=sum(1 for t in state.get('trace',[]) if t.get('success') is False)+int(last['status']=='PERSISTENCE_FAILED')
                metrics={'extraction_contract_correct':extraction_correct,
                    'decision_correct':last['status']==expected['status'],
                    'discrepancy_correct':controls.get('discrepancy_amount')==expected['discrepancy'],
                    'classification_correct':controls.get('classification')==expected['classification'],
                    'review_routing_correct':(last['event']=='awaiting_human_approval')==(expected['status']=='AWAITING_REVIEW'),
                    'retrieval_coverage_correct':len(state.get('facts',{}).get('policy',{}).get('policies',[]))==expected['retrieved_count'],
                    'tool_failure_detection_correct':failures==expected['tool_failures'],
                    'review_resume_and_duplicate_protection_correct':review_resume}
                results.append({'id':case['id'],'category':case['category'],'actual_status':last['status'],
                    'actual_discrepancy':controls.get('discrepancy_amount'),'metrics':metrics,'passed':all(v is not False for v in metrics.values()),
                    'latency_seconds':latency,'tool_failures':failures,'events':[e['event'] for e in events]})
    finally:
        if original_users is None: os.environ.pop('AUDIT_USERS_JSON',None)
        else: os.environ['AUDIT_USERS_JSON']=original_users
    categories={}
    for result in results:
        stats=categories.setdefault(result['category'],{'run':0,'passed':0,'skipped':0})
        if 'skipped' in result: stats['skipped']+=1
        else: stats['run']+=1; stats['passed']+=int(result['passed'])
    run=[r for r in results if 'skipped' not in r]
    report={'mode':'live' if live else 'offline-controlled','timestamp':datetime.now(timezone.utc).isoformat(),
        'model':Settings().model if live else 'controlled model responses; NOT Gemini accuracy',
        'policy_version':VERSION,'config':{'iterations':Settings().max_iterations,'tool_calls':Settings().max_tool_calls,'timeout_seconds':Settings().timeout,'retries':Settings().retries},
        'dependencies':{p:importlib.metadata.version(p) for p in ('google-genai','mcp','langgraph','pydantic')},
        'total_run':len(run),'passed':sum(r['passed'] for r in run),
        'mean_latency_seconds':sum(r['latency_seconds'] for r in run)/len(run) if run else None,
        'categories':categories,'cases':results}
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');p.add_argument('--confirm-test-database',action='store_true')
    p.add_argument('--dataset',default=str(Path(__file__).with_name('audit_benchmark_50.json')))
    p.add_argument('--output',default='evaluation/offline-results.json')
    a=p.parse_args()
    report=asyncio.run(evaluate(json.loads(Path(a.dataset).read_text(encoding='utf-8')),a.output,a.live,a.confirm_test_database))
    print(json.dumps({k:report[k] for k in ('mode','total_run','passed','mean_latency_seconds')}))
