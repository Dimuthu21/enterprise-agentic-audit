"""Authoritative rules. Retrieval text is generated from these same conditions."""
from decimal import Decimal

VERSION = '2026-09-07.1'
RULES = {
    'rule_101': {'absolute_lt': '100', 'percent_lt': '5', 'vendor': 'CLEAR'},
    'rule_102': {'absolute_gt': '500', 'percent_gt': '15'},
    'rule_103': {'review_statuses': ['FLAGGED', 'UNDER_REVIEW']},
    'rule_104': {'amount_gt': '2500', 'categories': ['Software', 'IT Services']},
}

def documents():
    a, b, c, d = (RULES[f'rule_{i}'] for i in range(101, 105))
    texts = [
        f"Overbilling strictly below USD {a['absolute_lt']} OR {a['percent_lt']} percent may be tolerated only for {a['vendor']} vendors, subject to all mandatory checks.",
        f"Overbilling strictly above USD {b['absolute_gt']} OR {b['percent_gt']} percent requires review and takes precedence over tolerance. Equality does not trigger this rule; amounts not covered by tolerance require review.",
        f"Vendor statuses {', '.join(c['review_statuses'])} always require authorized human review, including matching and underbilled invoices.",
        f"Purchases in {', '.join(d['categories'])} exceeding USD {d['amount_gt']} require independently verified SOW evidence attached to the PO. Unknown category or SOW is unresolved.",
    ]
    return [dict(policy_id=k, version=VERSION, text=t, conditions=v) for (k,v),t in zip(RULES.items(),texts)]

def enforce(invoice, po, vendor, web, evidence):
    findings, blocked = [], []
    def block(code):
        blocked.append(code)
        findings.append(code)
    try:
        approved = Decimal(str(po['approved_amount']))
        if not approved.is_finite() or approved <= 0:
            raise ValueError()
    except (KeyError, ValueError, ArithmeticError):
        return dict(findings=['invalid_po_amount'], blocked=['invalid_po_amount'], classification='unresolved', discrepancy_amount=None, discrepancy_percent=None)
    delta = invoice.billed_amount - approved
    percent = delta / approved * 100
    a, b, c, d = (RULES[f'rule_{i}'] for i in range(101,105))
    classification = 'matching' if delta == 0 else 'underbilling' if delta < 0 else 'material_overbilling'
    if po.get('currency') != invoice.currency: block('currency_mismatch_or_missing')
    if po.get('status') != 'OPEN': block('po_not_open')
    if po.get('po_number') != invoice.po_number: block('po_identity_mismatch')
    if vendor.get('vendor_id') != po.get('vendor_id'): block('vendor_id_mismatch')
    if vendor.get('vendor_name', '').casefold().strip() != invoice.vendor_name.casefold().strip(): block('vendor_identity_mismatch')
    risk = vendor.get('risk_status')
    if risk in c['review_statuses']: findings.append('vendor_requires_review')
    elif risk != a['vendor']: block('vendor_status_unresolved')
    if delta > 0:
        if delta > Decimal(b['absolute_gt']) or percent > Decimal(b['percent_gt']):
            findings.append('material_overage')
        elif (delta < Decimal(a['absolute_lt']) or percent < Decimal(a['percent_lt'])) and risk == a['vendor']:
            classification = 'tolerated_overbilling'
        else: findings.append('outside_tolerance')
    category = po.get('category')
    if not category: block('purchase_category_missing')
    elif category not in ['Hardware','Supplies',*d['categories']]: block('purchase_category_ambiguous')
    if category in d['categories'] and max(invoice.billed_amount, approved) > Decimal(d['amount_gt']):
        if po.get('sow_verified') is not True or not po.get('sow_reference'): block('sow_unverified')
    if web.get('assessment') != 'no_findings': findings.append('web_' + web.get('assessment', 'unavailable'))
    if web.get('mode') == 'demo': findings.append('demo_web_requires_review')
    expected = {x['policy_id']: x for x in documents()}
    retrieved = evidence.get('policies', [])
    if len(retrieved) != len(expected) or any(p != expected.get(p.get('policy_id')) for p in retrieved) or {p.get('policy_id') for p in retrieved} != set(expected):
        block('policy_evidence_missing_or_conflicting')
    return dict(findings=findings, blocked=blocked, classification=classification,
                discrepancy_amount=str(delta), discrepancy_percent=str(percent))
