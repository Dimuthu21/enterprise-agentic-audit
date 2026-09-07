import json
import asyncio
import os
import secrets
import uuid
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from backend.app.schemas import InvoiceAuditRequest, HumanApprovalRequest
from backend.app.service import AuditService, ServiceError
from backend.app import storage


def create_app(service=None):
    app=FastAPI(title='Invoice Audit API',version='2.0.0')
    app.state.service=service

    def get_service():
        if app.state.service is None: app.state.service=AuditService()
        return app.state.service

    def authenticate(authorization: str = Header(default='')):
        # Explicit local token authentication. Identity is server configured, never request supplied.
        try: users=json.loads(os.getenv('AUDIT_USERS_JSON','{}'))
        except ValueError: raise HTTPException(503,'Authentication configuration invalid')
        token=authorization.removeprefix('Bearer ')
        for identity,user in users.items():
            if user.get('token') and not user['token'].startswith('REPLACE_') and secrets.compare_digest(token,user['token']):
                return {'id':identity,'role':user.get('role')}
        raise HTTPException(401,'Valid bearer token required')

    def reviewer(user=Depends(authenticate)):
        if user['role']!='reviewer': raise HTTPException(403,'Reviewer role required')
        return user

    @app.exception_handler(ServiceError)
    async def service_error(request,exc): return JSONResponse(status_code=exc.code,content={'detail':exc.message})

    @app.get('/')
    def health():
        return {'status':'online','auth_mode':'local_tokens','web_mode':os.getenv('WEB_RISK_MODE','live'),
                'db_mode':os.getenv('DB_MODE','sqlserver'),'policy_mode':os.getenv('POLICY_MODE','chroma'),
                'extraction_mode':os.getenv('INVOICE_EXTRACTION_MODE','gemini')}

    @app.post('/api/audit/stream')
    async def stream(request:InvoiceAuditRequest,user=Depends(authenticate),svc=Depends(get_service)):
        thread=request.thread_id or str(uuid.uuid4())
        await asyncio.to_thread(svc.reserve,thread)
        async def events():
            async for event in svc.start(thread,request.invoice_text): yield {'data':json.dumps(event)}
        return EventSourceResponse(events(),ping=10)

    @app.post('/api/audit/approve')
    async def approve(request:HumanApprovalRequest,user=Depends(reviewer),svc=Depends(get_service)):
        try:
            result=await svc.approve(request.thread_id,request.approved,request.notes,user['id'])
            return JSONResponse(status_code=200 if result['event']=='completed' else 503,content=result)
        except ServiceError: raise
        except Exception: raise HTTPException(503,'Resume failed; decision retained; use retry') from None

    @app.post('/api/audit/{thread}/retry')
    async def retry(thread:str,user=Depends(reviewer),svc=Depends(get_service)):
        try:
            result=await svc.retry(thread)
            return JSONResponse(status_code=200 if result['event']!='error' else 503,content=result)
        except ServiceError: raise
        except Exception: raise HTTPException(503,'Retry failed; persistent state retained') from None

    @app.get('/api/audit/logs')
    def logs(user=Depends(authenticate)):
        try:
            data=storage.logs(); return {'count':len(data),'data':data}
        except Exception: raise HTTPException(503,'Audit store unavailable') from None

    @app.get('/api/audit/{thread}')
    async def status(thread:str,user=Depends(authenticate),svc=Depends(get_service)):
        return svc.public(thread,await svc.state(thread))

    return app

app=create_app()
