import pytest
from backend.app.config import Settings
from backend.app.mcp_client import MCPGateway,READ_TOOLS
from backend.app.storage import initialize_demo
from backend.app.web_risk import check

async def test_real_stdio_discovery_and_structured_results(tmp_path):
    path=str(tmp_path/'demo.sqlite'); initialize_demo(path)
    settings=Settings(db_mode='demo',demo_db=path,policy_mode='demo',web_mode='demo')
    async with MCPGateway(settings) as client:
        assert {t['name'] for t in client.read_schemas()}==READ_TOOLS
        po=await client.call('get_purchase_order',{'po_number':'PO-1001'})
        assert po.success and po.data['approved_amount']=='1200.00'
        vendor=await client.call('get_vendor_status',{'vendor_id':po.data['vendor_id']})
        assert vendor.success and vendor.data['risk_status']=='CLEAR'
        policies=await client.call('search_procurement_policies',{'query':'invoice controls'})
        assert policies.success and len(policies.data['policies'])==4
        web=await client.call('check_vendor_web_risk',{'vendor_name':vendor.data['vendor_name']})
        assert web.data['mode']=='demo' and web.data['assessment']=='unavailable'
        assert not (await client.call('record_audit_log',{})).success
        assert not (await client.call('get_purchase_order',{'bad':'PO-1001'})).success
        assert not (await client.call('get_purchase_order',{'po_number':123})).success
        record={'thread_id':'mcp-test','status':'REJECTED'}
        assert (await client.write(record)).data['persisted']
        assert (await client.write(record)).data['persisted']
        assert not (await client.write({**record,'status':'AUTO_APPROVED'})).success
        assert not (await client._invoke('record_audit_log',{'record':record,'capability':'wrong'})).success

def test_missing_web_credentials_not_demo(monkeypatch):
    monkeypatch.delenv('TAVILY_API_KEY',raising=False)
    result=check('Acme','live')
    assert result['mode']=='live' and result['assessment']=='unavailable'
async def test_graph_uses_actual_mcp_transport(tmp_path):
    from backend.app.service import AuditService
    from backend.app.benchmark.controlled import ControlledModel
    import sqlite3
    from contextlib import closing
    path=str(tmp_path/'erp.sqlite'); initialize_demo(path)
    settings=Settings(state_path=str(tmp_path/'graph.sqlite'),db_mode='demo',demo_db=path,policy_mode='demo',web_mode='demo')
    svc=AuditService(settings,lambda s:ControlledModel())
    svc.reserve('transport-graph')
    events=[e async for e in svc.start('transport-graph','Controlled model; real MCP transport')]
    assert events[-1]['status']=='AWAITING_REVIEW'
    assert 'demo_web_requires_review' in events[-1]['controls']['findings']
    restarted=AuditService(settings,lambda s:ControlledModel())
    assert (await restarted.approve('transport-graph',False,'Demo evidence not live','reviewer'))['status']=='REJECTED'
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT COUNT(*) FROM AuditRecords').fetchone()[0]==1
