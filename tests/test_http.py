import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from commitguard.adapters import FixturePlanner,FixturePayPal
from commitguard.server import make_handler
from commitguard.service import Service
from commitguard.store import Store

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.store=Store(Path(cls.tmp.name)/'http.sqlite3');cls.provider=FixturePayPal(cls.store);cls.service=Service(cls.store,FixturePlanner(),cls.provider)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),lambda *a:None);cls.port=cls.server.server_port;cls.server.RequestHandlerClass=make_handler(cls.service,cls.port);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.store.close();cls.tmp.cleanup()
    def setUp(self):
        self.cookie=None;status,headers,_=self.request('GET','/');self.assertEqual(status,200);self.cookie_attributes=headers['Set-Cookie'];self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=self.request('GET','/api/bootstrap')[2]['csrf']
    def request(self,method,path,body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        h={'Host':f'127.0.0.1:{self.port}'}
        if self.cookie:h['Cookie']=self.cookie
        if body is not None:h.update({'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}','X-CSRF-Token':getattr(self,'csrf','')})
        h.update(headers or {});payload=json.dumps(body).encode() if isinstance(body,(dict,list)) else body
        conn.request(method,path,payload,h);r=conn.getresponse();raw=r.read();headers=dict(r.getheaders());conn.close()
        try:data=json.loads(raw)
        except ValueError:data=raw.decode()
        return r.status,headers,data
    def plan(self):return self.request('POST','/api/plan',{'need':'Patches for 20 bike repairs','budget':'60.00','currency':'USD','request_key':'http-request-key-00001'})[2]
    def test_cookie_and_security_headers(self):
        self.assertTrue(self.cookie.startswith(f'cg_session_{self.port}='))
        status,h,_=self.request('GET','/');self.assertIn('HttpOnly',self.cookie_attributes);self.assertIn('SameSite=Lax',self.cookie_attributes)
        for k in ('Content-Security-Policy','X-Content-Type-Options','X-Frame-Options','Referrer-Policy'):self.assertIn(k,h)
        self.assertEqual(h['Cache-Control'],'no-store');self.assertIn("script-src 'self'",h['Content-Security-Policy']);self.assertNotIn('Access-Control-Allow-Origin',h)
    def test_get_does_not_mutate_payment(self):
        p=self.plan();status,_,_=self.request('GET','/api/capture?id='+p['id']);self.assertEqual(status,404);self.assertEqual(self.service.get(p['id'],self.cookie.split('=')[1])['state'],'DRAFT')
    def test_parallel_ports_keep_browser_cookie_sessions_separate(self):
        import http.cookiejar
        import urllib.request
        other_store=Store(Path(self.tmp.name)/'other-port.sqlite3')
        other_service=Service(other_store,FixturePlanner(),FixturePayPal(other_store))
        other=ThreadingHTTPServer(('127.0.0.1',0),lambda *a:None)
        other.RequestHandlerClass=make_handler(other_service,other.server_port)
        thread=threading.Thread(target=other.serve_forever,daemon=True);thread.start()
        try:
            jar=http.cookiejar.CookieJar()
            browser=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            def read(port,path):
                with browser.open(f'http://127.0.0.1:{port}{path}',timeout=5) as response:return response.read()
            read(self.port,'/')
            first=json.loads(read(self.port,'/api/bootstrap'))['csrf']
            read(other.server_port,'/')
            second=json.loads(read(other.server_port,'/api/bootstrap'))['csrf']
            self.assertNotEqual(first,second)
            self.assertEqual(json.loads(read(self.port,'/api/bootstrap'))['csrf'],first)
            self.assertEqual(json.loads(read(other.server_port,'/api/bootstrap'))['csrf'],second)
            self.assertEqual(len(list(jar)),2)
        finally:
            other.shutdown();other.server_close();thread.join();other_store.close()
    def test_missing_session_rejected(self):
        self.cookie=None;self.assertEqual(self.request('GET','/api/bootstrap')[0],401)
    def test_cross_origin_post_rejected(self):
        self.assertEqual(self.request('POST','/api/plan',{},headers={'Origin':'https://evil.invalid'})[0],403)
    def test_missing_csrf_rejected(self):
        self.assertEqual(self.request('POST','/api/plan',{},headers={'X-CSRF-Token':''})[0],403)
    def test_invalid_host_rejected(self):
        self.assertEqual(self.request('GET','/',headers={'Host':'evil.invalid'})[0],403)
    def test_body_limit(self):
        self.assertEqual(self.request('POST','/api/plan',b'x'*17000)[0],413)
    def test_bad_json_and_nonobject_rejected(self):
        self.assertEqual(self.request('POST','/api/plan',b'{')[0],400);self.assertEqual(self.request('POST','/api/plan',[])[0],400)
    def test_content_type_rejected(self):self.assertEqual(self.request('POST','/api/plan',b'{}',{'Content-Type':'text/plain'})[0],415)
    def test_static_traversal_and_data_files_unavailable(self):
        for path in ['/../commitguard/server.py','/.data/commitguard.sqlite3','/.env','/package-lock.json']:
            with self.subTest(path=path):self.assertEqual(self.request('GET',path)[0],404)
    def test_owner_cannot_access_other_session(self):
        p=self.plan();self.cookie=None;_,h,_=self.request('GET','/');self.cookie=h['Set-Cookie'].split(';')[0];self.assertEqual(self.request('GET','/api/purchases/'+p['id'])[0],404)
    def test_client_injected_amount_cannot_change_quote(self):
        body={'need':'Patches for 20 bike repairs','budget':'60.00','currency':'USD','request_key':'http-request-key-00001','total_cents':1}
        self.assertEqual(self.request('POST','/api/plan',body)[0],400)
    def test_api_rehearsal_end_to_end(self):
        p=self.plan();id=p['id']
        for action,extra in [('approve',{'plan_hash':p['plan_hash']}),('create',{}),('payer-fixture',{}),('capture',{}),('reconcile',{})]:
            status,_,p=self.request('POST','/api/'+action,{'id':id,**extra});self.assertEqual(status,200,p)
        self.assertEqual(p['state'],'COMPLETED');self.assertEqual(p['rehearsal_metrics'],{'capture_calls':1,'charge_count':1})
    def test_forged_webhook_rejected(self):
        status,_,body=self.request('POST','/api/webhook',{'id':'evil','event_type':'PAYMENT.CAPTURE.COMPLETED','resource':{}});self.assertEqual(status,401);self.assertEqual(body['error'],'WEBHOOK_SIGNATURE')
    def test_response_does_not_expose_owner_or_secret_names(self):
        p=self.plan();status,_,body=self.request('GET','/api/purchases/'+p['id']);self.assertEqual(status,200);self.assertNotIn('owner',body);self.assertNotIn('request_key',body)
        text=json.dumps(body)
        for secret in ['PAYPAL_CLIENT_SECRET','OPENAI_API_KEY','Authorization','Bearer ']:self.assertNotIn(secret,text)

if __name__=='__main__':unittest.main()
