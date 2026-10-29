"""Durable purchase orchestration. One capture invocation per immutable commitment."""
import copy
import re
import threading
import time
import uuid
from urllib.parse import urlsplit
from .policy import (CATALOG, MERCHANT, PolicyError, require, digest, validate_brief,
                     validate_proposal, order_body, inspect_order)
from .adapters import RemoteError

class Service:
    def __init__(self,store,planner,paypal,base_url='http://127.0.0.1:8765'):
        self.store,self.planner,self.paypal,self.base_url=store,planner,paypal,base_url
        self.lock=threading.RLock()
        with store.lock:
            for key,value in {'planner_mode':planner.mode,'payment_mode':paypal.mode}.items():
                previous=store.db.execute('SELECT value FROM metadata WHERE key=?',(key,)).fetchone()
                require(previous is None or previous[0]==value,'ADAPTER_PROVENANCE','This data directory belongs to different adapter modes. Use a separate --data-dir.',409)
        self.merchant=copy.deepcopy(MERCHANT)
        if paypal.mode=='sandbox':
            merchant_id=getattr(paypal,'merchant_id','')
            require(isinstance(merchant_id,str) and re.fullmatch(r'[A-Z0-9]{13}',merchant_id),'MERCHANT_CONFIG','Configure PAYPAL_MERCHANT_ID with the sandbox seller merchant ID.',503)
            self.merchant.update(id=merchant_id,name='Spoke Supply · fictional catalog, configured sandbox seller')
        with store.tx():
            modes={'planner_mode':planner.mode,'payment_mode':paypal.mode,'merchant_id':self.merchant['id']}
            for key,value in modes.items():
                previous=store.db.execute('SELECT value FROM metadata WHERE key=?',(key,)).fetchone()
                require(previous is None or previous[0]==value,'ADAPTER_PROVENANCE','This data directory belongs to different adapter modes. Use a separate --data-dir.',409)
                store.db.execute('INSERT OR IGNORE INTO metadata VALUES(?,?)',(key,value))
        # Any interrupted in-flight request has an uncertain outcome. Never resume a POST.
        with store.tx():
            for p in store.listing():
                # Reconstruct legacy cancellation intent from its durable trace even if
                # the old display state was later overwritten by provider reconciliation.
                cancellations=[e for e in p['trace'] if e['kind']=='LOCAL_CANCELLED']
                p.setdefault('local_cancelled_at',cancellations[0]['at'] if cancellations else (p.get('updated_at',p['created_at']) if p['state']=='CANCELLED' else None))
                p.setdefault('capture_observed',bool(p.get('capture_id')) or p['state'] in {'COMPLETED','PAYMENT_PENDING'})
                p.setdefault('provider_state',None)
                p.setdefault('last_capture_evidence',None)
                if p['state'] in {'CREATING','CAPTURING'}:
                    p['state']='CREATE_UNKNOWN' if p['state']=='CREATING' else 'CAPTURE_UNKNOWN'
                    self.trace(p,'PROCESS_RECOVERY','Interrupted request recovered. Only reconciliation is allowed.')
                store.save(p)
    def trace(self,p,kind,message):
        p['trace'].append({'at':time.time(),'kind':kind,'message':message})
        p['updated_at']=time.time()
    def _load(self,id,owner=None):
        p=self.store.get(id)
        require(p is not None and (owner is None or p['owner']==owner),'NOT_FOUND','Purchase not found.',404)
        return p
    def _save(self,p):
        with self.store.tx(): self.store.save(p)
        return self.public(p)
    def public(self,p):
        result={k:copy.deepcopy(v) for k,v in p.items() if k not in {'owner','request_key'}}
        result['planner_mode']=p['planner_mode']
        result['payment_mode']=p['payment_mode']
        if self.paypal.mode=='fixture' and p.get('paypal_id'):
            with self.store.lock:
                remote=self.store.fixture_get(p['paypal_id'])
            if remote:
                result['rehearsal_metrics']={k:remote[k] for k in ('capture_calls','charge_count')}
        return result
    def get(self,id,owner):
        with self.lock: return self.public(self._load(id,owner))
    def list(self,owner):
        with self.lock: return [self.public(p) for p in sorted(self.store.listing(owner),key=lambda p:p['created_at'],reverse=True)]
    def plan(self,owner,data):
        require(isinstance(data,dict),'BAD_REQUEST','Expected a JSON object.')
        request_key=data.get('request_key')
        require(isinstance(request_key,str) and re.fullmatch(r'[a-zA-Z0-9-]{16,64}',request_key),'REQUEST_KEY','A stable request key is required.')
        brief=validate_brief({k:v for k,v in data.items() if k!='request_key'})
        with self.lock:
            for p in self.store.listing(owner):
                if p['request_key']==request_key:
                    require(p['brief']==brief,'IDEMPOTENCY_CONFLICT','This request key belongs to a different brief.',409)
                    return self.public(p)
            raw=self.planner.propose(brief)
            plan=validate_proposal(raw,brief)
            plan['merchant']=copy.deepcopy(self.merchant)
            p={'planner_mode':self.planner.mode,'payment_mode':self.paypal.mode,'id':str(uuid.uuid4()),'owner':owner,'request_key':request_key,'brief':brief,'plan':plan,'plan_hash':digest(plan),'state':'DRAFT','approval_hash':None,'approved_at':None,'paypal_id':None,'capture_id':None,'approval_url':None,'create_key':str(uuid.uuid4()),'capture_key':str(uuid.uuid4()),'capture_started':False,'capture_observed':False,'local_cancelled_at':None,'provider_state':None,'last_capture_evidence':None,'created_at':time.time(),'trace':[]}
            self.trace(p,'PLAN_PROPOSED','Deterministic fixture proposal generated.' if self.planner.mode=='fixture' else 'Structured model proposed items. Server policy validated SKU, stock, currency and budget.')
            return self._save(p)
    def revise(self,id,owner,items):
        with self.lock:
            p=self._load(id,owner)
            require(p['state'] in {'DRAFT','APPROVED'},'LOCKED','Checkout has started. This commitment cannot be edited.',409)
            raw={'items':items,'explanation':'You adjusted the quantities. Server policy revalidated the complete quote.','questions':[]}
            plan=validate_proposal(raw,p['brief'])
            plan['merchant']=copy.deepcopy(self.merchant)
            require(plan['items'],'EMPTY_PLAN','Keep at least one item.')
            p.update(plan=plan,plan_hash=digest(plan),approval_hash=None,approved_at=None,state='DRAFT')
            self.trace(p,'APPROVAL_INVALIDATED','Items changed. Previous approval is invalid; review the new total.')
            return self._save(p)
    def approve(self,id,owner,plan_hash):
        with self.lock:
            p=self._load(id,owner)
            require(plan_hash==p['plan_hash'],'STALE_APPROVAL','The quote changed. Review the current quote.',409)
            if p['state']=='APPROVED': return self.public(p)
            require(p['state']=='DRAFT','STATE','This purchase cannot be approved now.',409)
            require(bool(p['plan']['items']) and not p['plan']['questions'],'CLARIFICATION','Resolve the planner questions before committing.',409)
            p.update(state='APPROVED',approval_hash=plan_hash,approved_at=time.time())
            self.trace(p,'COMMITMENT_APPROVED','Buyer approved exact items, quantities, fictional merchant, USD total and budget. This is separate from PayPal payer approval.')
            return self._save(p)
    def _commitment(self,p):
        require(not p.get('local_cancelled_at'),'LOCAL_CANCELLED','Local payment permission was revoked. Reconciliation cannot restore it.',409)
        require(p['approval_hash']==p['plan_hash']==digest(p['plan']),'APPROVAL_INVALID','Approval does not match the immutable quote.',409)
        require(time.time()-p['approved_at']<86400,'APPROVAL_EXPIRED','Approval is older than 24 hours. No capture will be attempted; review this purchase manually.',409)
    def create(self,id,owner):
        with self.lock:
            p=self._load(id,owner)
            if p['state']!='APPROVED':
                require(p['state'] not in {'DRAFT','CANCELLED'},'STATE','Approve this quote before checkout.',409)
                return self.public(p)  # Duplicate request does not send a second POST.
            self._commitment(p)
            unresolved={'CREATING','CREATE_UNKNOWN','CAPTURING','CAPTURE_UNKNOWN','PAYMENT_PENDING','REVIEW_REQUIRED'}
            require(not any(other['id']!=id and other['state'] in unresolved for other in self.store.listing(owner)), 'UNRESOLVED_PURCHASE','Another purchase in this browser has an unresolved payment outcome. Resolve it before creating a new checkout.',409)
            p['state']='CREATING'
            self.trace(p,'CREATE_RESERVED','Create intent and stable PayPal-Request-Id persisted before the provider call.')
            self._save(p)
            try:
                response=self.paypal.create(order_body(p['plan'],p['id'],self.base_url+'/?purchase='+p['id'],self.base_url+'/?cancelled='+p['id']),p['create_key'],p['brief']['scenario'])
                remote_id=response.get('id')
                require(isinstance(remote_id,str) and re.fullmatch(r'[A-Z0-9]{1,36}',remote_id),'PROVIDER_ID','Provider returned an invalid order ID.',502)
                p['paypal_id']=remote_id
                state,capture_id=inspect_order(response,p)
                require(state=='AWAITING_PAYER','PROVIDER_STATE','Unexpected order state at creation; manual review required.',409)
                p['state']=state
                urls=[l.get('href') for l in response.get('links',[]) if l.get('rel') in {'payer-action','approve'}]
                if self.paypal.mode=='sandbox':
                    require(len(urls)==1 and isinstance(urls[0],str),'PROVIDER_URL','Provider did not return one approval URL.',502)
                    u=urlsplit(urls[0])
                    require(u.scheme=='https' and u.hostname in {'www.sandbox.paypal.com','sandbox.paypal.com'} and u.port in (None,443) and not u.username and not u.password,'PROVIDER_URL','Untrusted approval URL rejected.',502)
                    p['approval_url']=urls[0]
                self.trace(p,'ORDER_CREATED','Order created. Waiting for the payer to approve at PayPal.' if self.paypal.mode=='sandbox' else 'Simulated order created. No PayPal request was sent.')
            except RemoteError as exc:
                p['state']='REVIEW_REQUIRED' if exc.definite else 'CREATE_UNKNOWN'
                self.trace(p,exc.code,'Order outcome requires review. Create will not be sent again. Use the saved request ID for merchant investigation.')
            except (PolicyError,TypeError,ValueError,KeyError,AttributeError):
                p['state']='REVIEW_REQUIRED' if p['paypal_id'] else 'CREATE_UNKNOWN'
                self.trace(p,'PROVIDER_CONTRACT','Unexpected create response. Checkout stopped for manual review.')
            return self._save(p)
    def payer_fixture(self,id,owner):
        require(self.paypal.mode=='fixture','FIXTURE_ONLY','Fixture controls are disabled in sandbox mode.',404)
        with self.lock:
            p=self._load(id,owner)
            require(not p.get('local_cancelled_at'),'LOCAL_CANCELLED','Local payment permission was revoked.',409)
            require(p['state'] in {'AWAITING_PAYER','READY_TO_CAPTURE'},'STATE','This fixture cannot be payer-approved now.',409)
            self.paypal.approve_fixture(p['paypal_id'])
            return self.reconcile(id,owner)
    def _record_provider(self,p,state,capture_id):
        # Payment evidence is independent of local authorization. Once a capture
        # was observed, stale/missing evidence can never authorize another POST.
        if capture_id:
            require(not p.get('capture_id') or p['capture_id']==capture_id,'PROVIDER_MISMATCH','Provider capture identity changed; manual review required.',409)
            p.update(capture_observed=True,capture_id=capture_id,last_capture_evidence={'id':capture_id,'state':state,'observed_at':time.time()})
        p['provider_state']=state
        if p.get('local_cancelled_at') and state not in {'COMPLETED','PAYMENT_PENDING','REVIEW_REQUIRED','CAPTURE_UNKNOWN'}:
            state='CANCELLED'
        p['state']=state

    def capture(self,id,owner):
        with self.lock:
            p=self._load(id,owner)
            require(not p.get('local_cancelled_at'),'LOCAL_CANCELLED','Local payment permission was revoked. No capture will be sent.',409)
            if p['capture_started'] or p.get('capture_observed'): return self.public(p)
            require(p['state']=='READY_TO_CAPTURE','STATE','Verify payer approval before capturing.',409)
            self._commitment(p)
            # Refresh provider facts immediately before the first and only capture call.
            try:
                state,capture_id=inspect_order(self.paypal.get(p['paypal_id']),p)
            except RemoteError:
                self.trace(p,'READ_UNAVAILABLE','Could not refresh payer approval. No capture was attempted.')
                return self._save(p)
            except (PolicyError,TypeError,ValueError,KeyError,AttributeError):
                p['state']='REVIEW_REQUIRED'
                self.trace(p,'PROVIDER_MISMATCH','Provider quote changed. Capture blocked.')
                return self._save(p)
            if state!='READY_TO_CAPTURE':
                self._record_provider(p,state,capture_id)
                self.trace(p,'CAPTURE_BLOCKED','Provider is no longer in the expected approved state. No capture was attempted.')
                return self._save(p)
            p.update(state='CAPTURING',capture_started=True)
            self.trace(p,'CAPTURE_RESERVED','Capture intent persisted. One capture POST is permitted for this commitment.')
            self._save(p)
            capture_returned=False
            try:
                self.paypal.capture(p['paypal_id'],p['capture_key'])
                capture_returned=True
                # Capture responses may omit original item fields. Read the full order
                # rather than inventing missing contract evidence.
                response=self.paypal.get(p['paypal_id'])
                state,capture_id=inspect_order(response,p,True)
                self._record_provider(p,state,capture_id)
                self.trace(p,'CAPTURE_RESPONSE','Capture response checked against the immutable USD commitment.')
            except RemoteError as exc:
                p['state']='REVIEW_REQUIRED' if exc.definite and not capture_returned else 'CAPTURE_UNKNOWN'
                self.trace(p,exc.code,'Post-capture order lookup failed. Capture may have succeeded; reconcile the original order. No payment retry.' if capture_returned else ('Provider rejected authentication; manual review required. No automatic retry.' if exc.definite else 'Capture response is missing. Payment may have succeeded. Reconcile the original order; do not pay again.'))
            except (PolicyError,TypeError,ValueError,KeyError,AttributeError):
                p['state']='REVIEW_REQUIRED'
                self.trace(p,'PROVIDER_MISMATCH','Unexpected capture evidence. Do not treat this purchase as paid; review at the merchant.')
            return self._save(p)
    def reconcile(self,id,owner=None):
        with self.lock:
            p=self._load(id,owner)
            require(p['paypal_id'],'NO_PROVIDER_ID','No provider order ID is known. Use the persisted create request ID for manual investigation; do not create another order.',409)
            if p['state']=='COMPLETED' and p.get('capture_id') and p.get('last_capture_evidence'): return self.public(p)
            try:
                state,capture_id=inspect_order(self.paypal.get(p['paypal_id']),p,p['capture_started'] or p.get('capture_observed',False))
                self._record_provider(p,state,capture_id)
                self.trace(p,'RECONCILED','Read original provider order. No create or capture request was sent.')
            except RemoteError:
                self.trace(p,'RECONCILE_UNAVAILABLE','Provider lookup unavailable. Existing payment status is unchanged; no payment retry was sent.')
            except (PolicyError,TypeError,ValueError,KeyError,AttributeError):
                p['state']='REVIEW_REQUIRED'
                self.trace(p,'PROVIDER_MISMATCH','Order or capture evidence differs from the commitment. Manual review required.')
            return self._save(p)
    def cancel(self,id,owner):
        with self.lock:
            p=self._load(id,owner)
            if p.get('local_cancelled_at'): return self.public(p)
            require(p['state'] in {'DRAFT','APPROVED','AWAITING_PAYER','READY_TO_CAPTURE'} and not p['capture_started'],'UNCERTAIN_PAYMENT','Cannot cancel a purchase after a capture attempt or while creation is uncertain. Reconcile it first.',409)
            p.update(state='CANCELLED',local_cancelled_at=time.time())
            self.trace(p,'LOCAL_CANCELLED','Stopped this app from attempting payment. This is not a PayPal void, refund or fulfillment cancellation.')
            return self._save(p)
    def webhook(self,headers,event,fixture_owner=None):
        require(isinstance(event,dict) and isinstance(event.get('id'),str) and 1<=len(event['id'])<=100,'BAD_EVENT','Malformed webhook event.')
        # Trust only cryptographic verification, or the separate authenticated fixture route.
        fixture=fixture_owner is not None and self.paypal.mode=='fixture'
        require(fixture or self.paypal.verify_webhook(headers,event),'WEBHOOK_SIGNATURE','Webhook signature is not verified.',401)
        supported={'CHECKOUT.ORDER.APPROVED','PAYMENT.CAPTURE.COMPLETED','PAYMENT.CAPTURE.PENDING','PAYMENT.CAPTURE.DENIED'}
        if event.get('event_type') not in supported: return {'accepted':True,'ignored':True}
        resource=event.get('resource',{})
        require(isinstance(resource,dict),'BAD_EVENT','Malformed resource.')
        if event['event_type']=='CHECKOUT.ORDER.APPROVED':
            provider_id=resource.get('id')
        else:
            extra=resource.get('supplementary_data',{})
            require(isinstance(extra,dict) and isinstance(extra.get('related_ids',{}),dict),'BAD_EVENT','Malformed related order data.')
            provider_id=extra.get('related_ids',{}).get('order_id')
        require(isinstance(provider_id,str) and re.fullmatch(r'[A-Z0-9]{1,36}',provider_id),'BAD_EVENT','Event does not identify a valid provider order.')
        with self.lock:
            match=next((p for p in self.store.listing() if p['paypal_id']==provider_id and (not fixture or p['owner']==fixture_owner)),None)
            if not match: return {'accepted':True,'ignored':True}
            if self.store.db.execute('SELECT 1 FROM events WHERE id=?',(event['id'],)).fetchone(): return {'accepted':True,'duplicate':True}
            result=self.reconcile(match['id'],match['owner'])
            # Failed lookup is not consumed, so a later delivery may retry reconciliation.
            if result['trace'][-1]['kind']=='RECONCILE_UNAVAILABLE': raise PolicyError('WEBHOOK_LOOKUP','Provider lookup unavailable; retry event later.',503)
            with self.store.tx(): self.store.db.execute('INSERT INTO events VALUES(?,?)',(event['id'],match['id']))
            return {'accepted':True,'purchase':result}
    def settle_fixture(self,id,owner):
        require(self.paypal.mode=='fixture','FIXTURE_ONLY','Fixture controls disabled.',404)
        with self.lock:
            p=self._load(id,owner)
            self.paypal.settle_fixture(p['paypal_id'])
            return self.reconcile(id,owner)
