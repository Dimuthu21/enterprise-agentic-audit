import os
import subprocess
import sys
from pathlib import Path
import pytest
from backend.app.config import Settings,ROOT
from backend.app.mcp_client import MCPGateway

async def test_cached_embedding_chroma_reindex_and_mcp(tmp_path,monkeypatch):
    cache=Path.home()/'.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2'
    if not cache.exists(): pytest.skip('Embedding not cached; run policy initialization first')
    for key,value in {'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','ANONYMIZED_TELEMETRY':'False','CHROMA_PATH':str(tmp_path/'chroma')}.items(): monkeypatch.setenv(key,value)
    import asyncio
    result=await asyncio.to_thread(subprocess.run,[sys.executable,'-m','backend.app.policy_index'],cwd=str(ROOT),env=os.environ.copy(),capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stderr[-2000:]
    async with MCPGateway(Settings(policy_mode='chroma',web_mode='demo',timeout=90)) as client:
        response=await client.call('search_procurement_policies',{'query':'Vendor review and SOW invoice tolerance'})
        assert response.success
        assert response.data['retrieval']=='chroma'
        assert {p['policy_id'] for p in response.data['policies']}=={'rule_101','rule_102','rule_103','rule_104'}
