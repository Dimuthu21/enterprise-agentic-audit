"""Pure event reducer shared by Streamlit and tests."""
def apply_event(state,event):
    state['thread_id']=event.get('thread_id',state.get('thread_id'))
    kind=event.get('event')
    if kind=='started': state.update(logs=[],pending=False,error=None,result=None)
    if kind=='node_update': state.setdefault('logs',[]).append(event['log'])
    if kind in ('awaiting_human_approval','completed','error'):
        state['pending']=kind=='awaiting_human_approval'
        state['result']=event
        state['error']=event.get('error') if kind=='error' else None
    return state
