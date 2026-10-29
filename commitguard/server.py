"""Loopback-only demo server. No hosted/multi-tenant security claim."""
import argparse
import json
import os
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from .adapters import FixturePlanner,FixturePayPal,StructuredModelPlanner,SandboxPayPal,RemoteError
from .policy import CATALOG,MERCHANT,PolicyError,require
from .service import Service
from .store import Store
from .process_lock import acquire_directory_lock

ROOT=Path(__file__).resolve().parent.parent

def make_handler(service,port):
    hosts={f'127.0.0.1:{port}',f'localhost:{port}'}
    cookie_name=f'cg_session_{port}'
    class Handler(BaseHTTPRequestHandler):
        server_version='CommitGuard'
        sys_version=''
        def log_message(self,*args): pass
        def send(self,status,data,content_type='application/json',cookie=None):
            body=json.dumps(data).encode() if content_type=='application/json' else data
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.send_header('X-Frame-Options','DENY')
            if cookie: self.send_header('Set-Cookie',cookie)
            self.end_headers()
            self.wfile.write(body)
        def owner(self):
            try:
                cookies=SimpleCookie(self.headers.get('Cookie',''))
                token=cookies[cookie_name].value if cookie_name in cookies else ''
            except Exception: token=''
            with service.store.lock:
                row=service.store.db.execute('SELECT csrf FROM sessions WHERE id=?',(token,)).fetchone()
            return (token,row[0]) if row else (None,None)
        def valid_host(self):
            require(self.headers.get('Host') in hosts,'HOST','Only the configured loopback origin is allowed.',403)
        def payload(self):
            require(self.headers.get('Content-Type','').split(';')[0]=='application/json','CONTENT_TYPE','Use application/json.',415)
            try: size=int(self.headers.get('Content-Length','0'))
            except ValueError: raise PolicyError('BODY','Invalid request size.')
            require(0<size<=16384,'BODY','Request must be between 1 and 16,384 bytes.',413)
            try: result=json.loads(self.rfile.read(size))
            except (ValueError,UnicodeError): raise PolicyError('JSON','Malformed JSON.') from None
            require(isinstance(result,dict),'JSON','Expected a JSON object.')
            return result
        def error(self,e):
            if isinstance(e,PolicyError): self.send(e.status,{'error':e.code,'message':e.message})
            else: self.send(500,{'error':'INTERNAL','message':'Request stopped unexpectedly. Reload and check the persisted purchase before taking another action.'})
        def do_GET(self):
            try:
                self.valid_host()
                path=urlsplit(self.path).path
                if path in {'/','/app.js','/style.css'}:
                    cookie=None
                    if path=='/' and not self.owner()[0]:
                        token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
                        with service.store.tx(): service.store.db.execute('INSERT INTO sessions VALUES(?,?)',(token,csrf))
                        cookie=f'{cookie_name}={token}; HttpOnly; SameSite=Lax; Path=/'
                    file={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]
                    ct={'/':'text/html; charset=utf-8','/app.js':'application/javascript; charset=utf-8','/style.css':'text/css; charset=utf-8'}[path]
                    return self.send(200,(ROOT/'web'/file).read_bytes(),ct,cookie)
                owner,csrf=self.owner()
                require(owner,'AUTH','Open the app first to establish a local session.',401)
                if path=='/api/bootstrap':
                    return self.send(200,{'csrf':csrf,'catalog':CATALOG,'merchant':service.merchant,'planner_mode':service.planner.mode,'payment_mode':service.paypal.mode,'purchases':service.list(owner)})
                if path.startswith('/api/purchases/'):
                    return self.send(200,service.get(path.rsplit('/',1)[1],owner))
                raise PolicyError('NOT_FOUND','Route not found.',404)
            except Exception as e: self.error(e)
        def do_POST(self):
            try:
                self.valid_host()
                path=urlsplit(self.path).path
                if path=='/api/webhook':
                    event=self.payload()
                    headers={k.lower():v for k,v in self.headers.items()}
                    return self.send(200,service.webhook(headers,event))
                owner,csrf=self.owner()
                require(owner,'AUTH','Local session required.',401)
                require(self.headers.get('Origin') in {'http://'+h for h in hosts},'ORIGIN','Request origin rejected.',403)
                require(secrets.compare_digest(self.headers.get('X-CSRF-Token',''),csrf),'CSRF','Request token rejected. Reload the app.',403)
                data=self.payload()
                if path=='/api/plan':
                    require(len(service.list(owner))<40,'LIMIT','This local session has reached its 40-plan limit.',429)
                    return self.send(200,service.plan(owner,data))
                id=data.get('id')
                require(isinstance(id,str),'ID','Purchase ID required.')
                handlers={
                    '/api/approve':lambda:service.approve(id,owner,data.get('plan_hash')),
                    '/api/revise':lambda:service.revise(id,owner,data.get('items')),
                    '/api/create':lambda:service.create(id,owner),
                    '/api/payer-fixture':lambda:service.payer_fixture(id,owner),
                    '/api/capture':lambda:service.capture(id,owner),
                    '/api/reconcile':lambda:service.reconcile(id,owner),
                    '/api/cancel':lambda:service.cancel(id,owner),
                    '/api/settle-fixture':lambda:service.settle_fixture(id,owner),
                    '/api/fixture-event':lambda:service.webhook({}, {'id':data.get('event_id'),'event_type':data.get('event_type','PAYMENT.CAPTURE.COMPLETED'),'resource':{'supplementary_data':{'related_ids':{'order_id':service.get(id,owner)['paypal_id']}}}},fixture_owner=owner),
                }
                require(path in handlers,'NOT_FOUND','Route not found.',404)
                return self.send(200,handlers[path]())
            except Exception as e: self.error(e)
    return Handler

def main():
    parser=argparse.ArgumentParser(description='Run CommitGuard on loopback, fixture modes by default.')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--data-dir',type=Path,default=ROOT/'.data')
    args=parser.parse_args()
    require(1024<=args.port<=65535,'PORT','Use a port between 1024 and 65535.')
    args.data_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    # File lock prevents competing processes from recovering another server's in-flight requests.
    lockfile=acquire_directory_lock(args.data_dir)
    store=Store(args.data_dir/'commitguard.sqlite3')
    planner_mode=os.environ.get('COMMITGUARD_PLANNER','fixture')
    payment_mode=os.environ.get('COMMITGUARD_PAYMENTS','fixture')
    require(planner_mode in {'fixture','model'} and payment_mode in {'fixture','sandbox'},'CONFIG','Unknown adapter mode.')
    allow=os.environ.get('COMMITGUARD_ALLOW_NETWORK')=='1'
    if (planner_mode=='model' or payment_mode=='sandbox') and not allow:
        raise SystemExit('External adapter selected but COMMITGUARD_ALLOW_NETWORK=1 is absent. No network request sent.')
    if planner_mode=='model' and not (os.environ.get('OPENAI_API_KEY') and os.environ.get('OPENAI_MODEL')):
        raise SystemExit('Model mode requires a server API key and explicit model ID. No external request sent.')
    if payment_mode=='sandbox' and not all(os.environ.get(name) for name in ('PAYPAL_CLIENT_ID','PAYPAL_CLIENT_SECRET','PAYPAL_MERCHANT_ID')):
        raise SystemExit('Sandbox mode requires app credentials and seller merchant ID. No external request sent.')
    planner=FixturePlanner() if planner_mode=='fixture' else StructuredModelPlanner(os.environ.get('OPENAI_API_KEY',''),os.environ.get('OPENAI_MODEL',''),allow)
    paypal=FixturePayPal(store) if payment_mode=='fixture' else SandboxPayPal(os.environ.get('PAYPAL_CLIENT_ID',''),os.environ.get('PAYPAL_CLIENT_SECRET',''),os.environ.get('PAYPAL_WEBHOOK_ID',''),allow,merchant_id=os.environ.get('PAYPAL_MERCHANT_ID',''))
    service=Service(store,planner,paypal,f'http://127.0.0.1:{args.port}')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(service,args.port))
    server.daemon_threads=True
    print(f'CommitGuard http://127.0.0.1:{args.port} | planner={planner.mode} | payments={paypal.mode}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close();store.close();lockfile.close()

if __name__=='__main__': main()
