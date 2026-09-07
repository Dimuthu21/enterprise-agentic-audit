"""Build explicit independent fixtures; expected decisions are specified, not inferred by the evaluator."""
import copy
import json
from decimal import Decimal
from pathlib import Path
from backend.app.benchmark.controlled import INVOICE,PO,VENDOR

SCENARIOS=[
    # name, PO amount, invoice amount, vendor risk, expected status, discrepancy, class
    ('matching','1200.00','1200.00','CLEAR','AUTO_APPROVED','0.00','matching'),
    ('underbilling','1200.00','1100.00','CLEAR','AUTO_APPROVED','-100.00','underbilling'),
    ('small_overage','1200.00','1299.99','CLEAR','AUTO_APPROVED','99.99','tolerated_overbilling'),
    ('absolute_tolerance_boundary','1200.00','1300.00','CLEAR','AWAITING_REVIEW','100.00','material_overbilling'),
    ('percentage_tolerance_below','10000.00','10499.99','CLEAR','AUTO_APPROVED','499.99','tolerated_overbilling'),
    ('percentage_tolerance_boundary','10000.00','10500.00','CLEAR','AWAITING_REVIEW','500.00','material_overbilling'),
    ('absolute_material_boundary','100000.00','100500.00','CLEAR','AUTO_APPROVED','500.00','tolerated_overbilling'),
    ('absolute_material_above','100000.00','100500.01','CLEAR','AWAITING_REVIEW','500.01','material_overbilling'),
    ('percentage_material_boundary','100.00','115.00','CLEAR','AUTO_APPROVED','15.00','tolerated_overbilling'),
    ('percentage_material_above','100.00','115.01','CLEAR','AWAITING_REVIEW','15.01','material_overbilling'),
    ('flagged_matching','1200.00','1200.00','FLAGGED','AWAITING_REVIEW','0.00','matching'),
    ('under_review_matching','1200.00','1200.00','UNDER_REVIEW','AWAITING_REVIEW','0.00','matching'),
]

def cases():
    output=[]
    for name,approved,billed,risk,status,delta,classification in SCENARIOS:
        for variant in range(4):
            invoice={**INVOICE,'invoice_id':f'INV-{len(output)+1}','billed_amount':billed}
            formatted=f'{Decimal(billed):,.2f}' if variant%2 else billed
            text=f"INVOICE ID: {invoice['invoice_id']}\nPO NUMBER: PO-1001\nVendor: Acme IT Solutions\nTotal Amount Billed: USD ${formatted}\nDescription: Hardware"
            output.append({'id':f'{name}_{variant}','category':name,'invoice_text':text,'model_response':invoice,
                'po':{**PO,'approved_amount':approved},'vendor':{**VENDOR,'risk_status':risk},
                'expected':{'status':status,'discrepancy':delta,'classification':classification,'extraction':invoice,'retrieved_count':4,'tool_failures':0}})
    for name,changes in [
        ('missing_amount',{'model_response':{**INVOICE,'billed_amount':None},'invoice_text':'INVOICE ID: INV-1\nPO NUMBER: PO-1001\nVendor: Acme IT Solutions\nCurrency: USD'}),
        ('malformed_po',{'model_response':{**INVOICE,'po_number':'invalid'},'invoice_text':'Invoice missing purchase order. USD $1200.00'}),
        ('missing_policy',{'policies':[]}),('vendor_unavailable',{'fail':'get_vendor_status'}),
        ('write_failure',{'fail':'write'}),('web_unavailable',{'web':{'mode':'live','assessment':'unavailable','sources':[]}}),
        ('sow_missing',{'po':{**PO,'approved_amount':'3000.00','category':'Software'},'model_response':{**INVOICE,'billed_amount':'3000.00'},'invoice_text':'INVOICE ID: INV-1\nPO NUMBER: PO-1001\nVendor: Acme IT Solutions\nTotal Amount Billed: USD $3000.00'}),
        ('comma_amount',{'model_response':{**INVOICE,'billed_amount':'$1,500.00'},'po':{**PO,'approved_amount':'1500.00'},'invoice_text':'INVOICE ID: INV-1\nPO NUMBER: PO-1001\nVendor: Acme IT Solutions\nTotal Amount Billed: USD $1,500.00'}),
    ]:
        case=copy.deepcopy(output[0]);case.update(changes);case.update(id=name,category=name)
        expected=case['expected']
        if name in ('missing_amount','malformed_po'):
            expected.update(status='VALIDATION_FAILED',discrepancy=None,classification=None,extraction=None,retrieved_count=0)
        elif name=='write_failure': expected.update(status='PERSISTENCE_FAILED',tool_failures=1)
        elif name=='comma_amount': expected['extraction']={**INVOICE,'billed_amount':'1500.00'}
        else:
            expected['status']='AWAITING_REVIEW'
            expected['extraction']=case['model_response']
        if name=='missing_policy': expected['retrieved_count']=0
        if name=='vendor_unavailable': expected['tool_failures']=1
        output.append(case)
    return output

if __name__=='__main__':
    path=Path(__file__).with_name('audit_benchmark_50.json')
    path.write_text(json.dumps(cases(),indent=2),encoding='utf-8')
    print(f'Wrote {len(cases())} cases to {path}')
