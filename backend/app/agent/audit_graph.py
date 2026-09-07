"""Mandatory controls and writes cannot be selected by the model."""
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from backend.app.agent.state import AuditAgentState
from backend.app.contracts import Invoice, Explanation
from backend.app.policies import enforce, VERSION

def build_graph(model, gateway, settings, checkpointer):
    async def extract(state):
        try:
            invoice=Invoice.model_validate(await model.extract(state['invoice_raw_text']))
            if invoice.issues: raise ValueError('Ambiguous or unsupported invoice')
            return {'invoice':invoice.model_dump(mode='json'), 'audit_status':'IN_PROGRESS',
                    'execution':{'model':settings.model,'extraction_mode':settings.extraction_mode,'policy_version':VERSION,'db_mode':settings.db_mode,
                                 'web_mode':settings.web_mode,'policy_mode':settings.policy_mode}}
        except Exception as exc:
            # Deliberately avoid returning provider payloads or invoice text, but make
            # the fix understandable to a local operator.
            message=str(exc)
            if 'GEMINI_API_KEY' in message:
                reason='Gemini is not configured. Add a valid GEMINI_API_KEY to .env, then restart the backend.'
            elif 'RESOURCE_EXHAUSTED' in message or '429' in message:
                reason='Gemini free-tier request quota is temporarily exhausted. Wait for the provider retry window, then start a new audit. Do not use Retry for this validation failure.'
            elif 'Invalid structured model response' in message:
                reason='Gemini returned an incomplete invoice. Try the provided invoice template again or submit a clearer source document.'
            elif 'Required extracted fields lack' in message or 'Ambiguous' in message:
                reason='Required source evidence is missing or ambiguous. Include invoice ID, PO number, vendor, USD, and one total amount.'
            else:
                reason='Gemini request failed or the selected model is unavailable. Check GEMINI_API_KEY, GEMINI_MODEL, and your internet connection.'
            return {'audit_status':'VALIDATION_FAILED','error':reason}

    async def evidence(state):
        inv=state['invoice']; facts={}; trace=[]
        async def required(name,args,key):
            result=await gateway.call(name,args)
            facts[key]=result.data if result.success else {}
            trace.append({'source':'mandatory','tool':name,'arguments':args,'success':result.success,'error':result.error,'result':result.data})
        await required('get_purchase_order',{'po_number':inv['po_number']},'po')
        if facts['po'].get('vendor_id'):
            await required('get_vendor_status',{'vendor_id':facts['po']['vendor_id']},'vendor')
        else:
            facts['vendor']={}
            trace.append({'source':'mandatory','tool':'get_vendor_status','success':False,'error':'vendor_id_unresolved'})
        await required('search_procurement_policies',{'query':'All mandatory invoice controls: tolerance, material overage, vendor risk and statement of work'},'policy')
        await required('check_vendor_web_risk',{'vendor_name':inv['vendor_name']},'web')
        return {'facts':facts,'trace':trace}

    async def select_tools(state):
        trace=list(state['trace']); used=0
        mandatory=[item for item in trace if item.get('source')=='mandatory']
        if mandatory and all(item.get('success') for item in mandatory):
            trace.append({'source':'application','success':True,'summary':'Optional model tool selection skipped because mandatory evidence is complete.'})
            return {'trace':trace}
        for iteration in range(settings.max_iterations):
            try:
                calls=await model.select({'invoice':state['invoice'],**state['facts']},gateway.read_schemas(),trace)
                if not calls: break
                if not isinstance(calls,list): raise ValueError()
                for call in calls:
                    if used >= settings.max_tool_calls: break
                    used+=1
                    name=call.get('name'); args=call.get('arguments')
                    result=await gateway.call(name,args)
                    trace.append({'source':'model_requested','tool':name,'arguments':args,'success':result.success,
                                  'error':result.error,'result':result.data,'summary':'Read-only evidence request processed'})
                if used >= settings.max_tool_calls: break
            except Exception:
                trace.append({'source':'model_requested','success':False,'error':'tool_selection_failed'})
                break
        return {'trace':trace}

    async def decide(state):
        facts=state['facts']
        controls=enforce(Invoice.model_validate(state['invoice']),facts['po'],facts['vendor'],facts['web'],facts['policy'])
        try:
            explanation=Explanation.model_validate(await model.explain({'invoice':state['invoice'],'database_facts':{'po':facts['po'],'vendor':facts['vendor']},
                'policy_evidence':facts['policy'],'web_evidence':facts['web'],'deterministic_controls':controls,'supplemental_evidence':state['trace']}))
            retrieved={(p['policy_id'],p['version']) for p in facts['policy'].get('policies',[])}
            citations={(c.policy_id,c.version) for c in explanation.citations}
            if not citations or not citations.issubset(retrieved): raise ValueError('Unretrieved citation')
            # Missing/conflicting policy evidence is a control failure. An
            # insufficient or irrelevant interpretation is still a safe review
            # outcome: an authorized reviewer may assess it with notes.
            if explanation.evidence_status in ('missing', 'conflicting'):
                controls['findings'].append('model_evidence_'+explanation.evidence_status)
                controls['blocked'].append('model_evidence_'+explanation.evidence_status)
            elif explanation.evidence_status != 'sufficient':
                controls['findings'].append('model_evidence_'+explanation.evidence_status)
            explanation=explanation.model_dump()
        except Exception:
            explanation={'summary':'Grounded model explanation unavailable or invalid','citations':[],'evidence_status':'insufficient'}
            controls['findings'].append('explanation_unverified'); controls['blocked'].append('explanation_unverified')
        return {'controls':controls,'explanation':explanation,'audit_status':'AWAITING_REVIEW' if controls['findings'] else 'READY_TO_PERSIST', 'intended_status':'AUTO_APPROVED'}

    def review(state):
        decision=interrupt({'status':'AWAITING_REVIEW','controls':state['controls'],'explanation':state['explanation']})
        if not isinstance(decision,dict) or decision.get('role') != 'reviewer' or not decision.get('reviewer_id') or not decision.get('timestamp'):
            raise ValueError('Authorized reviewer decision required')
        if decision['approved'] and state['controls']['blocked']:
            raise ValueError('Non-overridable findings require corrected evidence in a new audit')
        return {'review':decision,'audit_status':'READY_TO_PERSIST','intended_status':'MANUALLY_APPROVED' if decision['approved'] else 'REJECTED'}

    async def persist(state):
        record=state.get('record') or {'thread_id':state['thread_id'],'invoice':state['invoice'],
            'status':state['intended_status'],'controls':state['controls'],'explanation':state['explanation'],
            'review':state.get('review'),'execution':state['execution'],'created_at':state['created_at'],
            'evidence':state['facts'], 'tool_trace':state['trace']}
        try:
            result=await gateway.write(record)
            ok=result.success and result.data.get('persisted') is True and result.data.get('thread_id') == state['thread_id']
        except Exception: ok=False
        return {'record':record,'audit_status':record['status'] if ok else 'PERSISTENCE_FAILED', 'error':'' if ok else 'Audit persistence not confirmed'}

    graph=StateGraph(AuditAgentState)
    for name,node in [('extract',extract),('evidence',evidence),('select_tools',select_tools),('decide',decide),('review',review),('persist',persist)]: graph.add_node(name,node)
    graph.set_entry_point('extract')
    graph.add_conditional_edges('extract',lambda s: END if s['audit_status']=='VALIDATION_FAILED' else 'evidence')
    graph.add_edge('evidence','select_tools'); graph.add_edge('select_tools','decide')
    graph.add_conditional_edges('decide',lambda s:'review' if s['audit_status']=='AWAITING_REVIEW' else 'persist')
    graph.add_edge('review','persist'); graph.add_edge('persist',END)
    return graph.compile(checkpointer=checkpointer)
