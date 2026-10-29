import copy
import json
import http.client
from unittest.mock import patch
import unittest
from commitguard.adapters import SandboxPayPal,StructuredModelPlanner,FixturePlanner,RemoteError,PROPOSAL_SCHEMA
from commitguard.policy import PolicyError,order_body,validate_brief,validate_proposal

class AdapterContractTests(unittest.TestCase):
    def setUp(self):
        self.brief=validate_brief({'need':'Patches for 20 bike repairs','budget':'60.00','currency':'USD'})
        self.plan=validate_proposal(FixturePlanner().propose(self.brief),self.brief)
        self.calls=[]
    def transport(self,url,method,headers,body=None):
        self.calls.append((url,method,headers,body))
        if url.endswith('/token'):return {'access_token':'SERVER_TOKEN_ONLY'}
        if 'verify-webhook' in url:return {'verification_status':'SUCCESS'}
        return {'id':'ORDER123','status':'CREATED'}
    def test_sandbox_disabled_by_default(self):
        adapter=SandboxPayPal('id','secret',transport=self.transport)
        with self.assertRaises(PolicyError):adapter.create({},'stable-key')
        self.assertEqual(self.calls,[])
    def test_sandbox_only_fixed_host_and_documented_paths(self):
        adapter=SandboxPayPal('id','secret',allow_network=True,transport=self.transport)
        body=order_body(self.plan,'local-id','http://127.0.0.1:8765/','http://127.0.0.1:8765/')
        adapter.create(body,'CREATE-KEY');adapter.capture('ORDER123','CAPTURE-KEY');adapter.get('ORDER123')
        calls=[c for c in self.calls if not c[0].endswith('/token')]
        self.assertEqual([c[:2] for c in calls],[('https://api-m.sandbox.paypal.com/v2/checkout/orders','POST'),('https://api-m.sandbox.paypal.com/v2/checkout/orders/ORDER123/capture','POST'),('https://api-m.sandbox.paypal.com/v2/checkout/orders/ORDER123','GET')])
        self.assertEqual(calls[0][2]['PayPal-Request-Id'],'CREATE-KEY');self.assertEqual(calls[1][2]['PayPal-Request-Id'],'CAPTURE-KEY');self.assertEqual(calls[0][2]['Prefer'],'return=representation');self.assertEqual(json.loads(calls[1][3]),{})
    def test_token_uses_form_and_basic_credentials(self):
        adapter=SandboxPayPal('client','secret',allow_network=True,transport=self.transport);adapter.get('ORDER123')
        call=self.calls[0];self.assertEqual(call[0],'https://api-m.sandbox.paypal.com/v1/oauth2/token');self.assertEqual(call[2]['Content-Type'],'application/x-www-form-urlencoded');self.assertEqual(call[3],b'grant_type=client_credentials');self.assertTrue(call[2]['Authorization'].startswith('Basic '))
    def test_order_body_sums_items_and_has_no_client_amount(self):
        body=order_body(self.plan,'local-id','http://localhost/return','http://localhost/cancel');u=body['purchase_units'][0];self.assertEqual(body['intent'],'CAPTURE');self.assertEqual(u['amount']['value'],'12.00');self.assertEqual(u['amount']['breakdown']['item_total']['value'],'12.00');self.assertEqual(u['custom_id'],'local-id');self.assertEqual(u['payee']['merchant_id'],self.plan['merchant']['id'])
    def test_arbitrary_provider_path_rejected(self):
        adapter=SandboxPayPal('id','secret',allow_network=True,transport=self.transport)
        for id in ['../refund','https://evil.invalid','ORDER?x=1','A/B','',None]:
            with self.subTest(id=id):
                with self.assertRaises(PolicyError):adapter.capture(id,'key')
        self.assertEqual(self.calls,[])
    def test_signed_webhook_verification_contract(self):
        adapter=SandboxPayPal('id','secret','WEBHOOK-REAL',True,self.transport)
        headers={'paypal-auth-algo':'SHA256withRSA','paypal-cert-url':'https://api.sandbox.paypal.com/cert','paypal-transmission-id':'transmission','paypal-transmission-sig':'signature','paypal-transmission-time':'2026-10-29T00:00:00Z'}
        event={'id':'event','event_type':'PAYMENT.CAPTURE.COMPLETED'}
        self.assertTrue(adapter.verify_webhook(headers,event));request=self.calls[-1];body=json.loads(request[3]);self.assertEqual(request[0],'https://api-m.sandbox.paypal.com/v1/notifications/verify-webhook-signature');self.assertEqual(body['webhook_id'],'WEBHOOK-REAL');self.assertEqual(body['webhook_event'],event);self.assertEqual(body['transmission_sig'],'signature')
    def test_missing_webhook_headers_rejected_without_network(self):
        self.assertFalse(SandboxPayPal('id','secret','wh',True,self.transport).verify_webhook({},{}));self.assertEqual(self.calls,[])
    def model_transport(self,url,method,headers,body):
        self.calls.append((url,method,headers,body));return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'items':[{'sku':'PATCH20','quantity':1}],'explanation':'A safe proposal','questions':[]})}]}]}
    def test_model_disabled_by_default(self):
        with self.assertRaises(PolicyError):StructuredModelPlanner('key','explicit-model',transport=self.model_transport).propose(self.brief)
        self.assertEqual(self.calls,[])
    def test_structured_model_uses_responses_schema_and_no_tools(self):
        raw=StructuredModelPlanner('MODEL_SECRET','configured-model',True,self.model_transport).propose(self.brief);self.assertEqual(raw['items'][0]['sku'],'PATCH20');request=self.calls[0];body=json.loads(request[3]);self.assertEqual(request[0],'https://api.openai.com/v1/responses');self.assertEqual(body['text']['format']['schema'],PROPOSAL_SCHEMA);self.assertTrue(body['text']['format']['strict']);self.assertFalse(body['store']);self.assertNotIn('tools',body);self.assertNotIn('MODEL_SECRET',request[3].decode());self.assertIn('untrusted_catalog',json.loads(body['input']))
    def test_model_refusal_is_not_a_proposal(self):
        transport=lambda *a:{'status':'completed','output':[{'type':'message','content':[{'type':'refusal','refusal':'No'}]}]}
        with self.assertRaises(PolicyError):StructuredModelPlanner('key','model',True,transport).propose(self.brief)
    def test_incomplete_model_response_is_rejected(self):
        with self.assertRaises(PolicyError):StructuredModelPlanner('key','model',True,lambda *a:{'status':'incomplete','output':[]}).propose(self.brief)
    def test_malformed_model_output_is_rejected(self):
        transport=lambda *a:{'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'not JSON'}]}]}
        with self.assertRaises(PolicyError):StructuredModelPlanner('key','model',True,transport).propose(self.brief)
    def test_truncated_http_response_is_an_ambiguous_remote_error(self):
        from commitguard.adapters import http_json
        class BrokenOpener:
            def open(self,*args,**kw):raise http.client.IncompleteRead(b'partial provider response')
        with patch('urllib.request.build_opener',return_value=BrokenOpener()):
            with self.assertRaises(RemoteError) as caught:http_json('https://api-m.sandbox.paypal.com/v2/checkout/orders','POST',{},b'{}')
        self.assertFalse(caught.exception.definite)
        self.assertNotIn('partial',str(caught.exception))
    def test_deeply_nested_http_json_is_an_ambiguous_remote_error(self):
        from commitguard.adapters import http_json
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,*args):return b'['*5000+b']'*5000
        class Opener:
            def open(self,*args,**kw):return Response()
        with patch('urllib.request.build_opener',return_value=Opener()):
            with self.assertRaises(RemoteError) as caught:http_json('https://api.openai.com/v1/responses','POST',{},b'{}')
        self.assertFalse(caught.exception.definite)
    def test_model_auth_error_does_not_expose_provider_body(self):
        def transport(*a):raise RemoteError('PROVIDER_AUTH',True)
        with self.assertRaises(PolicyError) as e:StructuredModelPlanner('MODEL_SECRET','model',True,transport).propose(self.brief)
        self.assertNotIn('MODEL_SECRET',str(e.exception));self.assertEqual(e.exception.code,'MODEL_UNAVAILABLE')

if __name__=='__main__':unittest.main()
