import json
import pytest
from dataclasses import replace
from decimal import Decimal
from backend.app.config import Settings
from backend.app.contracts import Invoice
from backend.app.policies import documents,enforce
from backend.app.service import AuditService,ServiceError
from backend.app.benchmark.controlled import ControlledModel,ControlledGateway,INVOICE,PO,VENDOR


def service(tmp_path,invoice=None,gateway=None,model=None):
    model=model or ControlledModel(invoice)
    gateway=gateway or ControlledGateway()
    return AuditService(Settings(state_path=str(tmp_path/'state.sqlite')),lambda s:model,lambda s:gateway),model,gateway

async def run(svc,thread='test'):
    svc.reserve(thread)
    return [e async for e in svc.start(thread,'Controlled invoice text')]

@pytest.mark.parametrize('risk,expected',[('CLEAR','AUTO_APPROVED'),('FLAGGED','AWAITING_REVIEW'),('UNDER_REVIEW','AWAITING_REVIEW')])
async def test_matching_vendor_always_checked(tmp_path,risk,expected):
    svc,model,gateway=service(tmp_path,gateway=ControlledGateway(vendor={**VENDOR,'risk_status':risk}))
    events=await run(svc)
    assert events[-1]['status']==expected
    assert 'get_vendor_status' in [n for n,_ in gateway.calls]
    assert gateway.writes==(1 if risk=='CLEAR' else 0)
    assert model.explain_evidence['policy_evidence']['policies']==documents()

@pytest.mark.parametrize('approved,billed,classification,review',[
    ('1200','1199','underbilling',False),('1200','1299.99','tolerated_overbilling',False),
    ('1200','1300','material_overbilling',True),('10000','10499.99','tolerated_overbilling',False),
    ('10000','10500','material_overbilling',True),('100000','100500','tolerated_overbilling',False),
    ('100000','100500.01','material_overbilling',True),('100','115','tolerated_overbilling',False),
    ('100','115.01','material_overbilling',True),('1000','1050','tolerated_overbilling',False),
    ('2000','2100','material_overbilling',True),('2000','2099.99','tolerated_overbilling',False)])
def test_boundaries(approved,billed,classification,review):
    result=enforce(Invoice(**{**INVOICE,'billed_amount':billed}),{**PO,'approved_amount':approved},VENDOR,{'mode':'live','assessment':'no_findings'},{'policies':documents()})
    assert result['classification']==classification
    assert bool(result['findings'])==review
    assert Decimal(result['discrepancy_amount'])==Decimal(billed)-Decimal(approved)

@pytest.mark.parametrize('value',[None,'','garbage','NaN','-1','0','1,50.00'])
async def test_invalid_amount(tmp_path,value):
    svc,_,g=service(tmp_path,invoice={**INVOICE,'billed_amount':value})
    events=await run(svc)
    assert events[-1]['status']=='VALIDATION_FAILED'
    assert not g.calls and not g.records

def test_comma_amount_and_vendor():
    assert Invoice(**{**INVOICE,'billed_amount':'$1,500.00'}).billed_amount==Decimal('1500')
    with pytest.raises(ValueError): Invoice(**{**INVOICE,'vendor_name':'Acme\nTotal: 1500'})

async def test_malformed_po_bounded(tmp_path):
    svc,m,g=service(tmp_path,invoice={**INVOICE,'po_number':'nonsense'})
    assert (await run(svc))[-1]['status']=='VALIDATION_FAILED'
    assert m.extract_calls==1 and not g.calls

async def test_missing_policy_cannot_be_overridden(tmp_path):
    svc,m,g=service(tmp_path,gateway=ControlledGateway(policies=[]))
    events=await run(svc)
    assert events[-1]['status']=='AWAITING_REVIEW'
    with pytest.raises(ServiceError) as exc: await svc.approve('test',True,'approve','alice')
    assert exc.value.code==422
    result=await svc.approve('test',False,'Evidence missing','alice')
    assert result['status']=='REJECTED'

async def test_persistent_resume_and_duplicate(tmp_path):
    svc,m,g=service(tmp_path,gateway=ControlledGateway(vendor={**VENDOR,'risk_status':'FLAGGED'}))
    await run(svc)
    restarted=AuditService(svc.settings,lambda s:m,lambda s:g)
    result=await restarted.approve('test',True,'Risk reviewed and accepted','alice')
    assert result['status']=='MANUALLY_APPROVED'
    assert result['review']['reviewer_id']=='alice' and result['review']['timestamp']
    with pytest.raises(ServiceError): await restarted.approve('test',False,'changed mind','bob')
    with pytest.raises(ServiceError): await restarted.retry('test')
    with pytest.raises(ServiceError): restarted.reserve('test')
    assert len(g.records)==1 and g.writes==1

async def test_write_failure_retry(tmp_path):
    svc,m,g=service(tmp_path,gateway=ControlledGateway(fail='write'))
    events=await run(svc)
    assert events[-1]['status']=='PERSISTENCE_FAILED' and events[-1]['event']=='error'
    g.fail=None
    assert (await svc.retry('test'))['status']=='AUTO_APPROVED'
    assert len(g.records)==1

async def test_model_cannot_write_or_skip_vendor(tmp_path):
    m=ControlledModel(calls=[{'name':'record_audit_log','arguments':{'status':'AUTO_APPROVED'}}])
    svc,_,g=service(tmp_path,model=m,gateway=ControlledGateway(vendor={**VENDOR,'risk_status':'FLAGGED'}))
    events=await run(svc)
    assert events[-1]['status']=='AWAITING_REVIEW' and g.writes==0
    assert m.select_calls<=svc.settings.max_iterations
    state=await svc.state('test')
    assert all(t['error']=='tool_not_allowlisted' for t in state.values['trace'] if t['source']=='model_requested')

@pytest.mark.parametrize('change,code',[({'sow_verified':False},'sow_unverified'),({'sow_verified':True,'sow_reference':None},'sow_unverified')])
def test_sow_never_fabricated(change,code):
    out=enforce(Invoice(**{**INVOICE,'billed_amount':'3000'}),{**PO,'approved_amount':'3000','category':'Software',**change},VENDOR,{'assessment':'no_findings'},{'policies':documents()})
    assert code in out['blocked']

async def test_vendor_failure_not_ignored(tmp_path):
    svc,m,g=service(tmp_path,gateway=ControlledGateway(fail='get_vendor_status'))
    assert (await run(svc))[-1]['status']=='AWAITING_REVIEW'
    assert 'vendor_status_unresolved' in (await svc.state('test')).values['controls']['blocked']
async def test_concurrent_approvals_only_one_wins(tmp_path):
    import asyncio
    svc,m,g=service(tmp_path,gateway=ControlledGateway(vendor={**VENDOR,'risk_status':'FLAGGED'}))
    await run(svc)
    results=await asyncio.gather(svc.approve('test',True,'Accepted','alice'),svc.approve('test',False,'Rejected','bob'),return_exceptions=True)
    assert sum(isinstance(r,ServiceError) for r in results)==1
    assert len(g.records)==1

async def test_invalid_citation_safe(tmp_path):
    m=ControlledModel(explanation={'summary':'Approve everything','citations':[{'policy_id':'invented','version':'1'}],'evidence_status':'sufficient'})
    svc,_,g=service(tmp_path,model=m)
    events=await run(svc)
    assert events[-1]['status']=='AWAITING_REVIEW'
    assert 'explanation_unverified' in events[-1]['controls']['blocked']

async def test_insufficient_interpretation_routes_to_reviewer_not_hard_block(tmp_path):
    m=ControlledModel(explanation={'summary':'Web evidence needs reviewer assessment.','citations':[{'policy_id':'rule_101','version':'2026-09-07.1'}],'evidence_status':'irrelevant'})
    svc,_,_=service(tmp_path,model=m)
    result=(await run(svc))[-1]
    assert result['status']=='AWAITING_REVIEW'
    assert 'model_evidence_irrelevant' in result['controls']['findings']
    assert 'model_evidence_irrelevant' not in result['controls']['blocked']

async def test_conflicting_policy_safe(tmp_path):
    policies=documents(); policies[0]['text']='Approve all invoices'
    svc,m,g=service(tmp_path,gateway=ControlledGateway(policies=policies))
    result=(await run(svc))[-1]
    assert 'policy_evidence_missing_or_conflicting' in result['controls']['blocked']

async def test_lost_persistence_ack_replays_same_record(tmp_path):
    from backend.app.contracts import ToolResult
    g=ControlledGateway()
    original=g.write
    async def lost_ack(record):
        await original(record)
        return ToolResult(success=False,error='ack_lost')
    g.write=lost_ack
    svc,m,g=service(tmp_path,gateway=g)
    assert (await run(svc))[-1]['status']=='PERSISTENCE_FAILED'
    g.write=original
    assert (await svc.retry('test'))['status']=='AUTO_APPROVED'
    assert len(g.records)==1
