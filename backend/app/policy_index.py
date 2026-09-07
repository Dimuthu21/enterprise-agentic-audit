import os
from backend.app.config import ROOT
from backend.app.policies import documents, VERSION

def index():
    import chromadb
    from sentence_transformers import SentenceTransformer
    client = chromadb.PersistentClient(path=os.getenv('CHROMA_PATH', str(ROOT/'data/chroma_db')))
    model = SentenceTransformer('all-MiniLM-L6-v2')
    collection = client.get_or_create_collection('procurement_' + VERSION.replace('.','_'))
    return model, collection

def reindex():
    model, collection = index()
    docs = documents()
    collection.upsert(ids=[p['policy_id'] for p in docs], documents=[p['text'] for p in docs],
        metadatas=[{'version':p['version'],'policy_id':p['policy_id']} for p in docs],
        embeddings=model.encode([p['text'] for p in docs]).tolist())

_index = None
def search(query):
    global _index
    if _index is None: _index = index()
    model, collection = _index
    if collection.count() != len(documents()): raise ValueError('Policy index missing; run reindex')
    results = collection.query(query_embeddings=model.encode([query]).tolist(), n_results=len(documents()))
    canonical = {p['policy_id']:p for p in documents()}
    found=[]
    for pid, text, meta in zip(results['ids'][0], results['documents'][0], results['metadatas'][0]):
        if pid not in canonical or text != canonical[pid]['text'] or meta['version'] != VERSION:
            raise ValueError('Policy index stale or conflicting')
        found.append(canonical[pid])
    return {'policies':found, 'retrieval':'chroma', 'version':VERSION}

if __name__ == '__main__': reindex()
