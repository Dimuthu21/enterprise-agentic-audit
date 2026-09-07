import os
import re
import time
import httpx

def check(vendor_name, mode):
    if mode == 'demo':
        return {'mode':'demo', 'assessment':'unavailable', 'sources':[], 'reason':'Explicit simulation; no live evidence collected'}
    if mode != 'live': raise ValueError('Unsupported WEB_RISK_MODE')
    key = os.getenv('TAVILY_API_KEY')
    if not key:
        return {'mode':'live', 'assessment':'unavailable', 'sources':[], 'reason':'TAVILY_API_KEY missing'}
    for attempt in range(3):
        try:
            with httpx.Client(timeout=8) as client:
                response = client.post('https://api.tavily.com/search', json={'api_key':key,'query':f'"{vendor_name}" fraud litigation sanctions', 'max_results':5})
                response.raise_for_status()
                results = response.json()['results']
            normalize = lambda s: re.sub(r'\W+', ' ', s).casefold().strip()
            sources=[]
            for r in results:
                title, content = r.get('title',''),r.get('content','')
                matched = normalize(vendor_name) in normalize(title + ' ' + content)
                sources.append({'url':r['url'], 'date':r.get('published_date'), 'title':title,
                    'snippet':content[:2000], 'identity_match':'name_only' if matched else 'unconfirmed'})
            # Search hits are candidate evidence, not a finding of wrongdoing.
            return {'mode':'live','assessment':'risk_evidence_found' if any(s['identity_match']=='name_only' for s in sources) else 'identity_unresolved' if sources else 'no_findings',
                    'sources':sources,'reason':'Candidate search evidence requires human verification; absence is not proof of safety'}
        except (httpx.HTTPError, ValueError, KeyError):
            if attempt < 2: time.sleep(.25 * 2**attempt)
    return {'mode':'live','assessment':'unavailable','sources':[],'reason':'Provider failed after bounded retries'}

