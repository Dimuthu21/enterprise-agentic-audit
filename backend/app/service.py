import json
import asyncio
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from filelock import FileLock, Timeout
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from backend.app.agent.audit_graph import build_graph
from backend.app.config import Settings
from backend.app.gemini import Gemini, DeterministicDemoModel
from backend.app.mcp_client import MCPGateway

FINAL = {'AUTO_APPROVED','MANUALLY_APPROVED','REJECTED'}

@contextmanager
def registry_connection(path):
    db=sqlite3.connect(path,timeout=1)
    try:
        with db: yield db
    finally: db.close()

class ServiceError(Exception):
    def __init__(self, code, message): self.code=code; self.message=message

class AuditService:
    def __init__(self, settings=None, model_factory=None, gateway_factory=MCPGateway):
        self.settings=settings or Settings()
        self.model_factory=model_factory or (DeterministicDemoModel if self.settings.extraction_mode=='demo_deterministic' else Gemini)
        self.gateway_factory=gateway_factory
        Path(self.settings.state_path).parent.mkdir(parents=True,exist_ok=True)
        self.registry=self.settings.state_path+'.registry'
        with registry_connection(self.registry) as db:
            db.execute('CREATE TABLE IF NOT EXISTS Threads(id TEXT PRIMARY KEY, decision TEXT)')

    def lock(self, thread):
        import hashlib
        return FileLock(self.registry+'.'+hashlib.sha256(thread.encode()).hexdigest()+'.lock',timeout=0,thread_local=False)

    def reserve(self, thread):
        try:
            with registry_connection(self.registry) as db: db.execute('INSERT INTO Threads(id) VALUES (?)',(thread,))
        except sqlite3.IntegrityError: raise ServiceError(409,'Thread ID already used; use a new ID') from None

    def registered(self,thread):
        with registry_connection(self.registry) as db: return db.execute('SELECT decision FROM Threads WHERE id=?',(thread,)).fetchone()

    @asynccontextmanager
    async def runtime(self):
        model=self.model_factory(self.settings)
        try:
            async with self.gateway_factory(self.settings) as gateway:
                async with AsyncSqliteSaver.from_conn_string(self.settings.state_path) as saver:
                    yield build_graph(model,gateway,self.settings,saver)
        finally:
            await model.close()

    async def state(self, thread):
        if not await asyncio.to_thread(self.registered,thread): raise ServiceError(404,'Thread not found')
        async with AsyncSqliteSaver.from_conn_string(self.settings.state_path) as saver:
            graph=build_graph(None,None,self.settings,saver)
            return await graph.aget_state({'configurable':{'thread_id':thread}})

    def public(self,thread,state):
        v=state.values; status=v.get('audit_status','ERROR')
        return {'thread_id':thread,'status':status,'controls':v.get('controls'), 'explanation':v.get('explanation'),
            'execution':v.get('execution'),'review':v.get('review'),'error':v.get('error'),
            'event':'awaiting_human_approval' if status=='AWAITING_REVIEW' else 'completed' if status in FINAL and v.get('record') and not state.next else 'error'}

    async def start(self,thread,text):
        try:
            with self.lock(thread):
                async with self.runtime() as graph:
                    config={'configurable':{'thread_id':thread}}
                    yield {'event':'started','thread_id':thread,'status':'IN_PROGRESS'}
                    async for update in graph.astream({'thread_id':thread,'invoice_raw_text':text,'trace':[],
                            'created_at':datetime.now(timezone.utc).isoformat()},config,stream_mode='updates'):
                        for name,value in update.items():
                            if name=='__interrupt__': continue
                            yield {'event':'node_update','thread_id':thread,'node':name,'log':f'{name} finished',
                                   'status':value.get('audit_status','IN_PROGRESS') if isinstance(value,dict) else 'IN_PROGRESS'}
                    yield self.public(thread,await graph.aget_state(config))
        except Exception:
            yield {'event':'error','thread_id':thread,'status':'ERROR','error':'Execution unavailable; inspect saved state and use retry when configured'}

    async def approve(self,thread,approved,notes,reviewer):
        try:
            with self.lock(thread):
                row=await asyncio.to_thread(self.registered,thread)
                if not row: raise ServiceError(404,'Thread not found')
                state=await self.state(thread)
                if row[0] or state.values.get('audit_status')!='AWAITING_REVIEW' or 'review' not in state.next:
                    raise ServiceError(409,'Thread is not awaiting an undecided review')
                if approved and state.values['controls']['blocked']:
                    raise ServiceError(422,'Non-overridable evidence failures: reject or submit corrected evidence as a new audit')
                decision={'approved':approved,'notes':notes,'reviewer_id':reviewer,'role':'reviewer','timestamp':datetime.now(timezone.utc).isoformat()}
                await asyncio.to_thread(self.save_decision,thread,decision)
                return await self._resume(thread,decision)
        except Timeout: raise ServiceError(409,'Thread is busy') from None

    def save_decision(self,thread,decision):
        with registry_connection(self.registry) as db:
            updated=db.execute('UPDATE Threads SET decision=? WHERE id=? AND decision IS NULL',(json.dumps(decision),thread)).rowcount
            if updated!=1: raise ServiceError(409,'Decision already recorded')

    async def _resume(self,thread,decision=None,retry=False):
        config={'configurable':{'thread_id':thread}}
        async with self.runtime() as graph:
            state=await graph.aget_state(config)
            if retry and state.values.get('audit_status')=='PERSISTENCE_FAILED':
                await graph.aupdate_state(config,{'audit_status':'PERSISTING'},as_node='review')
            await graph.ainvoke(Command(resume=decision) if decision and 'review' in state.next else None,config)
            return self.public(thread,await graph.aget_state(config))

    async def retry(self,thread):
        try:
            with self.lock(thread):
                row=await asyncio.to_thread(self.registered,thread)
                if not row: raise ServiceError(404,'Thread not found')
                state=await self.state(thread)
                if not state.values: raise ServiceError(409,'No checkpoint exists; submit a new audit')
                if state.values.get('audit_status') in FINAL and not state.next: raise ServiceError(409,'Audit already completed')
                if state.values.get('audit_status')=='VALIDATION_FAILED': raise ServiceError(409,'Submit corrected invoice as a new audit')
                if 'review' in state.next and not row[0]: raise ServiceError(409,'An authorized review decision is required')
                return await self._resume(thread,json.loads(row[0]) if row[0] else None,retry=True)
        except Timeout: raise ServiceError(409,'Thread is busy') from None
