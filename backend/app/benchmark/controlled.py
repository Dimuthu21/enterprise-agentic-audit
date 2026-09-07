"""Controlled offline responses. These never represent Gemini accuracy."""
import copy
from backend.app.contracts import Invoice, Explanation, ToolResult
from backend.app.policies import documents, VERSION
from backend.app.mcp_client import READ_TOOLS

INVOICE={'invoice_id':'INV-1','po_number':'PO-1001','vendor_name':'Acme IT Solutions','billed_amount':'1200.00','currency':'USD'}
PO={'po_number':'PO-1001','vendor_id':'VEND-001','approved_amount':'1200.00','currency':'USD','status':'OPEN','category':'Hardware','sow_verified':None,'sow_reference':None}
VENDOR={'vendor_id':'VEND-001','vendor_name':'Acme IT Solutions','risk_status':'CLEAR'}

class ControlledModel:
    def __init__(self,invoice=None,calls=None,explanation=None):
        self.invoice=copy.deepcopy(invoice if invoice is not None else INVOICE)
        self.calls=calls or []
        self.explanation=explanation
        self.extract_calls=0
        self.select_calls=0
        self.explain_evidence=None
    async def extract(self,text):
        self.extract_calls+=1
        return Invoice.model_validate(self.invoice)
    async def select(self,facts,tools,history):
        self.select_calls+=1
        return self.calls
    async def explain(self,evidence):
        self.explain_evidence=evidence
        return Explanation.model_validate(self.explanation or {'summary':'Controlled offline explanation based on supplied evidence.',
            'citations':[{'policy_id':p['policy_id'],'version':p['version']} for p in evidence['policy_evidence'].get('policies',[])],
            'evidence_status':'sufficient'})
    async def close(self): pass

class ControlledGateway:
    def __init__(self,po=None,vendor=None,policies=None,web=None,fail=None):
        self.po=copy.deepcopy(PO if po is None else po)
        self.vendor=copy.deepcopy(VENDOR if vendor is None else vendor)
        self.policies=copy.deepcopy(documents() if policies is None else policies)
        self.web=web or {'mode':'live','assessment':'no_findings','sources':[]}
        self.fail=fail; self.records={}; self.calls=[]; self.writes=0
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    def read_schemas(self):
        return [{'name':name,'description':'Controlled read-only fixture','inputSchema':{'type':'object'}} for name in READ_TOOLS]
    async def call(self,name,args):
        self.calls.append((name,args))
        if name not in READ_TOOLS: return ToolResult(success=False,error='tool_not_allowlisted')
        if self.fail==name: return ToolResult(success=False,error='controlled_tool_failure')
        data={'get_purchase_order':self.po,'get_vendor_status':self.vendor,
              'search_procurement_policies':{'policies':self.policies,'retrieval':'controlled'},'check_vendor_web_risk':self.web}[name]
        return ToolResult(success=True,data=data)
    async def write(self,record):
        self.writes+=1
        if self.fail=='write': return ToolResult(success=False,error='controlled_write_failure')
        if record['thread_id'] in self.records and self.records[record['thread_id']] != record: return ToolResult(success=False,error='conflict')
        self.records[record['thread_id']]=copy.deepcopy(record)
        return ToolResult(success=True,data={'persisted':True,'thread_id':record['thread_id']})
