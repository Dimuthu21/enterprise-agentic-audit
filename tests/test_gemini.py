import pytest
from types import SimpleNamespace
from backend.app.gemini import Gemini, response_schema_for
from backend.app.config import Settings
from backend.app.contracts import Invoice, Explanation
from backend.app.benchmark.controlled import INVOICE

async def test_structured_retry_is_bounded():
    model=object.__new__(Gemini); model.settings=Settings(retries=2)
    calls=[]
    async def generate(*args,**kwargs):
        calls.append(1); return SimpleNamespace(text='{"po_number":"bad"}')
    model.generate=generate
    with pytest.raises(ValueError): await model.structured('invoice',Invoice)
    assert len(calls)==3

async def test_structured_recovery():
    model=object.__new__(Gemini); model.settings=Settings(retries=2)
    import json
    responses=iter(['garbage',json.dumps({**INVOICE,'billed_amount':'$1,500.00'})])
    async def generate(*args,**kwargs): return SimpleNamespace(text=next(responses))
    model.generate=generate
    assert str((await model.structured('invoice',Invoice)).billed_amount)=='1500.00'

async def test_explanation_status_case_is_normalized():
    model=object.__new__(Gemini); model.settings=Settings(retries=0)
    async def generate(*args,**kwargs):
        return SimpleNamespace(text='{"summary":"Evidence reviewed.","citations":[],"evidence_status":"Sufficient"}')
    model.generate=generate
    result=await model.structured('explain',Explanation)
    assert result.evidence_status=='sufficient'

def test_real_sdk_config_constructs():
    from google.genai import types
    config=types.GenerateContentConfig(response_mime_type='application/json',response_schema=Invoice,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    assert config.automatic_function_calling.disable
    declaration=types.FunctionDeclaration(name='get_purchase_order',parameters_json_schema={'type':'object','properties':{'po_number':{'type':'string'}}})
    assert declaration.parameters_json_schema

def test_google_response_schemas_are_sdk_compatible():
    from google.genai import types
    assert types.Schema.model_validate(response_schema_for(Invoice)).type == 'OBJECT'
    assert types.Schema.model_validate(response_schema_for(Explanation)).type == 'OBJECT'
async def test_source_grounding_and_comma_extraction():
    model=object.__new__(Gemini)
    async def structured(*args): return Invoice(**{**INVOICE,'billed_amount':'$1,500.00'})
    model.structured=structured
    text='INVOICE ID: INV-1\nPO NUMBER: PO-1001\nVendor: Acme IT Solutions\nTotal: USD $1,500.00'
    assert str((await model.extract(text)).billed_amount)=='1500.00'
    with pytest.raises(ValueError): await model.extract(text.replace('1,500','1,200'))
    with pytest.raises(ValueError): await model.extract(text.replace('USD ',''))
    with pytest.raises(ValueError): await model.extract(text.replace('Acme IT Solutions','Other vendor'))

async def test_optional_fields_are_not_required_for_a_valid_invoice():
    model=object.__new__(Gemini)
    async def structured(*args): return Invoice(**INVOICE)
    model.structured=structured
    text='INVOICE ID: INV-1\nPO NUMBER: PO-1001\nVendor: Acme IT Solutions\nTotal: USD $1,200.00'
    assert (await model.extract(text)).description is None
