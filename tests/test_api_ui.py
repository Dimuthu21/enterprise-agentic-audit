import json
import os
import pytest
import httpx
from backend.app.main import create_app
from backend.app.ui_events import apply_event
from backend.app.config import Settings
from backend.app.service import AuditService
from backend.app.benchmark.controlled import ControlledModel,ControlledGateway,VENDOR

@pytest.fixture
def users(monkeypatch):
    monkeypatch.setenv('AUDIT_USERS_JSON',json.dumps({'alice':{'role':'reviewer','token':'review-test'},'bob':{'role':'submitter','token':'submit-test'}}))

async def test_api_review_auth_resume_and_sse(tmp_path,users):
    g=ControlledGateway(vendor={**VENDOR,'risk_status':'UNDER_REVIEW'})
    svc=AuditService(Settings(state_path=str(tmp_path/'state.sqlite')),lambda s:ControlledModel(),lambda s:g)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(svc)),base_url='http://test') as c:
        assert (await c.post('/api/audit/stream',json={'invoice_text':'x'})).status_code==401
        headers={'Authorization':'Bearer submit-test'}
        response=await c.post('/api/audit/stream',headers=headers,json={'invoice_text':'x','thread_id':'api-test'})
        events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        assert events[0]['event']=='started'
        assert len([e for e in events if e['event']=='node_update'])>=4
        assert events[-1]['event']=='awaiting_human_approval'
        assert not any(e['event']=='completed' for e in events)
        request={'thread_id':'api-test','approved':True,'notes':'Risk verified'}
        assert (await c.post('/api/audit/approve',headers=headers,json=request)).status_code==403
        headers={'Authorization':'Bearer review-test'}
        request['reviewer_id']='forged'
        assert (await c.post('/api/audit/approve',headers=headers,json=request)).status_code==422
        del request['reviewer_id']
        response=await c.post('/api/audit/approve',headers=headers,json=request)
        assert response.status_code==200 and response.json()['review']['reviewer_id']=='alice'
        assert (await c.post('/api/audit/approve',headers=headers,json=request)).status_code==409
        assert (await c.post('/api/audit/stream',headers=headers,json={'invoice_text':'x','thread_id':'api-test'})).status_code==409
        assert (await c.get('/api/audit/missing',headers=headers)).status_code==404
        request['thread_id']='missing'
        assert (await c.post('/api/audit/approve',headers=headers,json=request)).status_code==404
        assert len(g.records)==1

async def test_sse_error_never_completed(tmp_path,users):
    svc=AuditService(Settings(state_path=str(tmp_path/'state.sqlite')),lambda s:ControlledModel(),lambda s:ControlledGateway(fail='write'))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(svc)),base_url='http://test') as c:
        response=await c.post('/api/audit/stream',headers={'Authorization':'Bearer review-test'},json={'invoice_text':'x'})
        events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        assert events[-1]['event']=='error'
        assert not any(e.get('status')=='AUTO_APPROVED' for e in events)

async def test_stream_yields_before_completion(tmp_path):
    g=ControlledGateway()
    svc=AuditService(Settings(state_path=str(tmp_path/'state.sqlite')),lambda s:ControlledModel(),lambda s:g)
    svc.reserve('incremental')
    events=svc.start('incremental','x')
    assert (await anext(events))['event']=='started'
    assert not g.records
    assert (await anext(events))['event']=='node_update'
    assert not g.records
    rest=[e async for e in events]
    assert rest[-1]['event']=='completed'

def test_ui_event_reducer():
    state={}
    apply_event(state,{'event':'started','thread_id':'abc'})
    apply_event(state,{'event':'node_update','log':'extract finished'})
    assert state['logs']==['extract finished'] and not state['pending']
    apply_event(state,{'event':'awaiting_human_approval'})
    assert state['pending']
    apply_event(state,{'event':'completed','status':'REJECTED'})
    assert not state['pending'] and state['result']['status']=='REJECTED'
    apply_event(state,{'event':'error','error':'failed'})
    assert state['error']=='failed' and not state['pending']
def test_streamlit_renders_during_stream(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from types import SimpleNamespace
    import streamlit as st
    import requests
    import sseclient
    from pathlib import Path
    class Response:
        ok=True
        def json(self): return {'db_mode':'demo','policy_mode':'demo','web_mode':'demo'}
        def raise_for_status(self): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
    observed=[]
    class Client:
        def __init__(self,response): pass
        def events(self):
            yield SimpleNamespace(data=json.dumps({'event':'started','thread_id':'ui-thread'}))
            yield SimpleNamespace(data=json.dumps({'event':'node_update','log':'extract finished'}))
            observed.append(list(st.session_state.audit['logs']))
            yield SimpleNamespace(data=json.dumps({'event':'awaiting_human_approval','status':'AWAITING_REVIEW','controls':{'blocked':[]}}))
    monkeypatch.setattr(requests,'get',lambda *a,**k:Response())
    monkeypatch.setattr(requests,'post',lambda *a,**k:Response())
    monkeypatch.setattr(sseclient,'SSEClient',Client)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'backend/app/app_ui.py')).run()
    assert not app.exception
    next(field for field in app.text_input if field.label=='Reviewer access token').set_value('reviewer-token').run()
    next(b for b in app.button if b.label=='Start audit').click().run()
    assert not app.exception
    assert observed==[['extract finished']]
    assert app.session_state.audit['pending']
    assert any('Review is required' in w.value for w in app.warning)
