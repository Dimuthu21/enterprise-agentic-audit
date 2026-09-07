import json
from backend.app.benchmark.generate_benchmark import cases
from backend.app.benchmark.run_evals import evaluate

async def test_evaluator_runs_graph_and_api_not_categories(tmp_path):
    dataset=cases()[:1]
    dataset[0]['category']='HIGH_RISK_VENDOR_MISLEADING_REPORT_LABEL'
    report=await evaluate(dataset,tmp_path/'result.json')
    assert report['passed']==1
    assert report['cases'][0]['actual_status']=='AUTO_APPROVED'
    assert report['cases'][0]['events'].count('node_update')>=5
    assert report['cases'][0]['latency_seconds']>0
    saved=json.loads((tmp_path/'result.json').read_text())
    assert saved['mode']=='offline-controlled'

async def test_bad_expectation_is_reported(tmp_path):
    dataset=cases()[:1]; dataset[0]['expected']['status']='REJECTED'
    report=await evaluate(dataset,tmp_path/'result.json')
    assert report['passed']==0 and not report['cases'][0]['metrics']['decision_correct']
