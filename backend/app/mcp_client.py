import asyncio
import os
import secrets
import sys
from contextlib import AsyncExitStack
from datetime import timedelta
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from jsonschema import validate
from backend.app.config import ROOT
from backend.app.contracts import ToolResult

READ_TOOLS = frozenset({'get_purchase_order','get_vendor_status','search_procurement_policies','check_vendor_web_risk'})

class MCPGateway:
    def __init__(self, settings):
        self.settings=settings
        self.capability=secrets.token_urlsafe(32)

    async def __aenter__(self):
        self.stack=AsyncExitStack()
        await self.stack.__aenter__()
        try:
            env={**os.environ,'AUDIT_WRITE_CAPABILITY':self.capability,
                 'AUDIT_MCP_CHILD':'1',
                 'DB_MODE':self.settings.db_mode,'DB_CONNECTION_STRING':self.settings.db_connection,
                 'DEMO_DB_PATH':self.settings.demo_db,'POLICY_MODE':self.settings.policy_mode,'WEB_RISK_MODE':self.settings.web_mode}
            streams=await self.stack.enter_async_context(stdio_client(StdioServerParameters(command=sys.executable,
                args=['-m','mcp_servers.audit_server'], cwd=str(ROOT), env=env)))
            self.session=await self.stack.enter_async_context(ClientSession(*streams, read_timeout_seconds=timedelta(seconds=self.settings.timeout)))
            await asyncio.wait_for(self.session.initialize(),self.settings.timeout)
            listed=await asyncio.wait_for(self.session.list_tools(),self.settings.timeout)
            self.schemas={t.name:{'name':t.name,'description':t.description or '', 'inputSchema':t.inputSchema} for t in listed.tools}
            if not READ_TOOLS.union({'record_audit_log'}).issubset(self.schemas): raise ValueError('Required MCP tools missing')
            return self
        except BaseException:
            await self.stack.aclose()
            raise

    async def __aexit__(self,*args): await self.stack.__aexit__(*args)

    def read_schemas(self): return [self.schemas[n] for n in sorted(READ_TOOLS)]

    async def _invoke(self,name,args):
        try:
            schema=self.schemas[name]['inputSchema']
            validate(args,{**schema,'additionalProperties':False})
            response=await asyncio.wait_for(self.session.call_tool(name,args),self.settings.timeout)
            if response.isError or response.structuredContent is None:
                return ToolResult(success=False,error='mcp_tool_error')
            return ToolResult.model_validate(response.structuredContent)
        except TimeoutError:
            return ToolResult(success=False,error='mcp_timeout')
        except Exception:
            return ToolResult(success=False,error='invalid_arguments_or_tool_failure')

    async def call(self,name,args):
        if name not in READ_TOOLS: return ToolResult(success=False,error='tool_not_allowlisted')
        return await self._invoke(name,args)

    async def write(self,record):
        return await self._invoke('record_audit_log',{'record':record,'capability':self.capability})
