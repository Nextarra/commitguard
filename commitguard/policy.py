"""Deterministic purchasing authority. Model output is never payment authority."""
import hashlib
import json
import re

CATALOG = [
    {'sku':'PATCH20','name':'Puncture patches · 20 pack','category':'patches','price_cents':1200,'stock':8,'coverage':20,'description':'Self-adhesive patches for workshop tube repairs.'},
    {'sku':'LEVER6','name':'Tyre levers · set of 6','category':'tools','price_cents':900,'stock':5,'coverage':6,'description':'Reusable composite levers; no metal edges.'},
    {'sku':'GLOVE50','name':'Nitrile gloves · 50 pairs','category':'safety','price_cents':1600,'stock':4,'coverage':50,'description':'Latex-free workshop protection.'},
    {'sku':'LUBE250','name':'Chain lubricant · 250 ml','category':'lubricant','price_cents':1100,'stock':6,'coverage':25,'description':'For routine drivetrain maintenance.'},
    {'sku':'CLOTH10','name':'Reusable cloths · 10 pack','category':'cleaning','price_cents':700,'stock':10,'coverage':10,'description':'Washable workshop cleaning cloths.'},
    {'sku':'TUBE700','name':'700c inner tubes · pair','category':'tubes','price_cents':1800,'stock':6,'coverage':2,'description':'700 x 28–35c, Presta valve. Confirm fit before buying.'},
]
MERCHANT = {'id':'WORKSHOP_FIXTURE','name':'Spoke Supply · fictional merchant','currency':'USD','catalog_version':'2026-10-29.1'}
CATEGORIES = {p['category'] for p in CATALOG}

class PolicyError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status

def require(ok, code, message, status=400):
    if not ok:
        raise PolicyError(code, message, status)

def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True)

def digest(data):
    return hashlib.sha256(canonical(data).encode()).hexdigest()

def money(cents):
    return f'{cents // 100}.{cents % 100:02d}'

def parse_money(value):
    require(isinstance(value, str) and re.fullmatch(r'(0|[1-9][0-9]{0,5})\.[0-9]{2}', value), 'BAD_AMOUNT', 'Use a positive USD amount with two decimal places.')
    cents = int(value.replace('.', ''))
    require(100 <= cents <= 100000, 'BAD_BUDGET', 'Budget must be between $1.00 and $1,000.00.')
    return cents

def validate_brief(data):
    require(isinstance(data, dict) and set(data) <= {'need','budget','currency','scenario'}, 'BAD_BRIEF', 'Unsupported brief fields.')
    need = data.get('need')
    require(isinstance(need,str) and 8 <= len(need.strip()) <= 1200, 'BAD_NEED', 'Describe the workshop need in 8–1,200 characters.')
    require(data.get('currency') == 'USD', 'CURRENCY', 'This prototype supports USD only.')
    budget = parse_money(data.get('budget'))
    scenario = data.get('scenario','lost_response')
    require(scenario in {'happy','lost_response','timeout_before','pending','auth_error','create_timeout','mismatch'}, 'SCENARIO', 'Unknown rehearsal scenario.')
    return {'need':need.strip(),'budget_cents':budget,'currency':'USD','scenario':scenario}

def validate_proposal(raw, brief, catalog=CATALOG):
    require(isinstance(raw,dict) and set(raw)=={'items','explanation','questions'}, 'MODEL_SCHEMA', 'Planner output did not match the allowed schema.')
    require(isinstance(raw['explanation'],str) and 1 <= len(raw['explanation']) <= 1200, 'MODEL_SCHEMA','Planner explanation is invalid.')
    require(isinstance(raw['questions'],list) and len(raw['questions']) <= 3 and all(isinstance(q,str) and 1 <= len(q) <= 200 for q in raw['questions']), 'MODEL_SCHEMA','Planner questions are invalid.')
    require(isinstance(raw['items'],list) and len(raw['items']) <= 6,'MODEL_SCHEMA','Planner proposed too many items.')
    products={p['sku']:p for p in catalog}
    lines=[]
    seen=set()
    for line in raw['items']:
        require(isinstance(line,dict) and set(line)=={'sku','quantity'}, 'MODEL_SCHEMA','Only catalog SKU and quantity are allowed.')
        sku, qty=line['sku'],line['quantity']
        require(isinstance(sku,str) and sku in products and sku not in seen, 'MODEL_SKU','Planner selected an unknown or duplicate SKU.')
        p=products[sku]
        require(type(qty) is int and 1 <= qty <= min(10,p['stock']), 'MODEL_QUANTITY','Quantity exceeds stock or policy.')
        seen.add(sku)
        lines.append({'sku':sku,'quantity':qty,'name':p['name'],'unit_cents':p['price_cents'],'line_cents':p['price_cents']*qty})
    total=sum(l['line_cents'] for l in lines)
    require(total <= brief['budget_cents'], 'OVER_BUDGET','Planner proposal exceeds the approved budget. Nothing was ordered.')
    require(bool(lines) or bool(raw['questions']), 'EMPTY_PLAN','Planner must propose items or ask a clarifying question.')
    return {'items':sorted(lines,key=lambda l:l['sku']),'total_cents':total,'budget_cents':brief['budget_cents'],'currency':'USD','merchant':MERCHANT,'explanation':raw['explanation'],'questions':raw['questions'],'need':brief['need']}

def order_body(plan, local_id, return_url, cancel_url):
    amount={'currency_code':plan['currency'],'value':money(plan['total_cents'])}
    return {'intent':'CAPTURE','purchase_units':[{'reference_id':local_id,'custom_id':local_id,'invoice_id':local_id,'payee':{'merchant_id':plan['merchant']['id']},'amount':{**amount,'breakdown':{'item_total':amount}},'items':[{'name':l['name'],'sku':l['sku'],'quantity':str(l['quantity']),'unit_amount':{'currency_code':plan['currency'],'value':money(l['unit_cents'])},'category':'PHYSICAL_GOODS'} for l in plan['items']]}], 'payment_source':{'paypal':{'experience_context':{'return_url':return_url,'cancel_url':cancel_url,'user_action':'PAY_NOW','shipping_preference':'NO_SHIPPING'}}}}

def inspect_order(remote, purchase, require_capture=False):
    """Validate identity, original quote and authoritative capture evidence."""
    plan=purchase['plan']
    require(isinstance(remote,dict) and remote.get('id')==purchase['paypal_id'], 'PROVIDER_MISMATCH','Provider order identity differs from the committed order.',409)
    require(remote.get('intent')=='CAPTURE','PROVIDER_MISMATCH','Provider order intent differs from the commitment.',409)
    units=remote.get('purchase_units',[])
    require(isinstance(units,list) and len(units)==1,'PROVIDER_MISMATCH','Unexpected provider purchase units.',409)
    unit=units[0]
    expected={'currency_code':plan['currency'],'value':money(plan['total_cents'])}
    require(unit.get('reference_id')==purchase['id'] and unit.get('custom_id')==purchase['id'] and unit.get('amount',{}).get('currency_code')==expected['currency_code'] and unit.get('amount',{}).get('value')==expected['value'], 'PROVIDER_MISMATCH','Order amount, currency or reference differs from the committed quote.',409)
    require(unit.get('payee',{}).get('merchant_id')==plan['merchant']['id'],'PROVIDER_MISMATCH','Provider merchant differs from the committed seller.',409)
    returned_items=unit.get('items')
    expected_items=[{'sku':line['sku'],'name':line['name'],'quantity':str(line['quantity']),'unit_amount':{'currency_code':plan['currency'],'value':money(line['unit_cents'])}} for line in plan['items']]
    require(isinstance(returned_items,list) and len(returned_items)==len(expected_items) and all(isinstance(item,dict) for item in returned_items),'PROVIDER_MISMATCH','Provider items are missing or differ from the commitment.',409)
    normalized=[{k:item.get(k) for k in ('sku','name','quantity','unit_amount')} for item in returned_items]
    require(sorted(normalized,key=canonical)==sorted(expected_items,key=canonical),'PROVIDER_MISMATCH','Provider SKU, name, quantity or unit price differs from the commitment.',409)
    captures=unit.get('payments',{}).get('captures',[])
    require(isinstance(captures,list) and len(captures)<=1,'PROVIDER_MISMATCH','Unexpected multiple captures; manual review required.',409)
    if captures:
        c=captures[0]
        require(isinstance(c,dict) and c.get('amount')==expected and isinstance(c.get('id'),str) and re.fullmatch(r'[A-Z0-9]{1,36}',c['id']), 'PROVIDER_MISMATCH','Capture amount or currency differs from the commitment.',409)
        if c.get('status')=='COMPLETED' and remote.get('status')=='COMPLETED':
            return 'COMPLETED', c['id']
        if c.get('status')=='PENDING':
            return 'PAYMENT_PENDING', c['id']
        return 'REVIEW_REQUIRED', c['id']
    if require_capture:
        return 'CAPTURE_UNKNOWN',None
    if remote.get('status')=='APPROVED':
        return 'READY_TO_CAPTURE',None
    if remote.get('status') in {'CREATED','PAYER_ACTION_REQUIRED'}:
        return 'AWAITING_PAYER',None
    return 'REVIEW_REQUIRED',None
