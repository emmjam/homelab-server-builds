"""Independent HTTP cookie jars; these are not real-device/browser tests."""
import http.cookiejar
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'RufusWeb'))
from auth import Auth,Throttled,password_hash,password_valid,decode_hash
from web import handler

PASSWORD='Disposable test-only passphrase 123'

class HTTPClient:
    def __init__(self,url):
        self.url=url;self.cookies=http.cookiejar.CookieJar();self.csrf=''
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(self.cookies))
    def call(self,path,body=None,origin=True,csrf=True,headers=None):
        request_headers=dict(headers or {})
        if body is not None:
            request_headers['Content-Type']='application/x-www-form-urlencoded' if path=='/login' else 'application/json'
            if origin:request_headers.setdefault('Origin',self.url)
            if csrf:request_headers.setdefault('X-CSRF-Token',self.csrf)
        data=(urllib.parse.urlencode(body).encode() if path=='/login' else json.dumps(body).encode()) if body is not None else None
        request=urllib.request.Request(self.url+path,data=data,headers=request_headers)
        try:
            with self.opener.open(request,timeout=15) as response:status,payload,h=response.status,response.read(),response.headers
        except urllib.error.HTTPError as error:status,payload,h=error.code,error.read(),error.headers
        text=payload.decode()
        if path=='/' and status==200 or path=='/login' and status==200:
            pattern=r'name="csrf-token" content="([^"]+)"' if 'csrf-token' in text else r'name="csrf" value="([^"]+)"'
            match=re.search(pattern,text)
            if match:self.csrf=match[1]
        return status,text,h
    def login(self,name='ian',password=PASSWORD):
        self.call('/')
        return self.call('/login',{'username':name,'password':password,'csrf':self.csrf})
    def token(self):return next(c.value for c in self.cookies if c.name=='rufus_web')

class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.encoded=password_hash(PASSWORD)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.now=1000
        self.accounts=Path(self.temp.name)/'accounts.json'
        self.records=[{'id':'operator-1','username':'ian','enabled':True,'version':'1','password_hash':self.encoded},
                      {'id':'operator-2','username':'other','enabled':True,'version':'1','password_hash':self.encoded}]
        self.write_accounts()
        self.config={'database':self.temp.name+'/db','accounts_file':str(self.accounts),'allowed_origins':[]}
        self.auth=Auth(self.config,lambda:self.now)
        self.upstream=Mock();self.upstream.token='server-only-api-bearer';self.upstream.request.return_value=(200,{'conversations':[]})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.config,self.auth,self.upstream))
        self.url='http://127.0.0.1:'+str(self.server.server_port);self.config['allowed_origins']=[self.url]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.stop)
        self.a,self.b=HTTPClient(self.url),HTTPClient(self.url)
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def write_accounts(self):self.accounts.write_text(json.dumps(self.records))
    def test_scrypt_salts_parameters_and_wrong_password(self):
        other=password_hash(PASSWORD);self.assertNotEqual(other,self.encoded)
        self.assertEqual(len(decode_hash(other)[0]),16)
        self.assertTrue(password_valid(PASSWORD,self.encoded));self.assertFalse(password_valid('wrong',self.encoded))
        with self.assertRaises(ValueError):password_hash('ab')
        with self.assertRaises(ValueError):password_hash('x'*1025)
        self.assertNotIn(PASSWORD,self.accounts.read_text())
    def test_authentication_generic_failures_and_no_unauthenticated_proxy(self):
        self.assertEqual(self.a.call('/api/conversations')[0],401)
        failures=[]
        for name,password in [('ian','wrong'),('unknown','wrong')]:
            status,text,_=self.a.login(name,password);self.assertEqual(status,401);failures.append(text)
        self.records[0]['enabled']=False;self.write_accounts()
        status,text,_=self.a.login();self.assertEqual(status,401);failures.append(text)
        self.assertEqual(len(set(failures)),1);self.upstream.request.assert_not_called()
    def test_independent_sessions_cookie_security_fixation_logout_and_replay(self):
        self.assertEqual(self.a.login()[0],200);self.assertEqual(self.b.login()[0],200)
        old=self.a.token();self.assertNotEqual(old,self.b.token())
        cookie=next(c for c in self.a.cookies if c.name=='rufus_web')
        self.assertIn('HttpOnly',cookie._rest);self.assertEqual(cookie._rest['SameSite'],'Strict');self.assertFalse(cookie.domain_specified)
        self.assertEqual(self.a.call('/logout',{})[0],200)
        self.assertEqual(self.a.call('/api/conversations',headers={'Cookie':'rufus_web='+old})[0],401)
        self.assertEqual(self.b.call('/api/conversations')[0],200)
        self.a.login();self.assertNotEqual(self.a.token(),old)
        with self.auth.db() as db:
            row=db.execute('SELECT * FROM web_sessions_v2 WHERE hash=?',(self.auth.digest(self.b.token()),)).fetchone()
            self.assertNotEqual(row['hash'],self.b.token());self.assertEqual(row['expires'],1000+28800)
    def test_session_absolute_expiry_and_restart(self):
        self.a.login();token=self.a.token();self.now+=100
        reopened=Auth(self.config,lambda:self.now);self.assertIsNotNone(reopened.session(token))
        self.a.call('/api/conversations');self.now=1000+28800
        self.assertIsNone(reopened.session(token));self.assertEqual(self.a.call('/api/conversations')[0],401)
    def test_csrf_all_mutations_and_cross_session_tokens(self):
        self.a.login();self.b.login();ident='a'*8+'-'+ 'b'*4+'-'+ 'c'*4+'-'+ 'd'*4+'-'+ 'e'*12
        paths=['/logout','/api/conversations','/api/conversations/'+ident+'/messages','/api/actions/'+ident+'/decision']
        for path in paths:
            self.assertEqual(self.a.call(path,{},csrf=False)[0],403)
            self.assertEqual(self.a.call(path,{},headers={'X-CSRF-Token':self.b.csrf})[0],403)
            self.assertEqual(self.a.call(path,{},origin=False,csrf=False)[0],403)
            self.assertEqual(self.a.call(path,{},headers={'Origin':'null'},csrf=False)[0],403)
            self.assertEqual(self.a.call(path,{},headers={'Origin':'http://evil.example'})[0],403)
        self.upstream.request.assert_not_called()
        self.assertEqual(self.a.call('/api/conversations',{},origin=False)[0],200)
        self.assertEqual(self.a.call('/api/conversations',{},headers={'Origin':'null'})[0],200)
        self.assertEqual(self.a.call('/')[2]['Referrer-Policy'],'same-origin')
    def test_login_csrf_preauth_replay_expiry_and_host(self):
        self.a.call('/');csrf=self.a.csrf;pre=next(c.value for c in self.a.cookies if c.name=='rufus_pre')
        self.assertEqual(self.a.call('/login',{'username':'ian','password':PASSWORD,'csrf':'wrong'})[0],403)
        self.assertEqual(self.a.call('/login',{'username':'ian','password':PASSWORD,'csrf':'wrong'},origin=False)[0],403)
        self.assertEqual(self.a.call('/login',{'username':'ian','password':PASSWORD,'csrf':csrf})[0],200)
        self.assertFalse(self.auth.pre_csrf(pre,csrf))
        self.b.call('/');self.now+=900
        self.assertEqual(self.b.call('/login',{'username':'ian','password':PASSWORD,'csrf':self.b.csrf})[0],403)
        self.assertEqual(self.a.call('/',headers={'Host':'evil.example:9999'})[0],403)
    def test_simple_in_memory_peer_limit_and_expiry(self):
        with patch('auth.password_valid',return_value=False):
            for n in range(20):self.assertEqual(self.a.login(name='unknown'+str(n),password='wrong')[0],401)
            self.assertEqual(self.b.login(password='wrong')[0],429)
            reopened=Auth(self.config,lambda:self.now)
            reopened.check_limits('127.0.0.1') # Deliberately not persistent.
            with self.auth.db() as db:
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='failures'").fetchone())
            self.now+=901
            self.assertEqual(self.a.login(password='wrong')[0],401)
    def test_bounded_concurrent_hashing_and_atomic_failures(self):
        entered,release=threading.Event(),threading.Event()
        def slow(*args):entered.set();release.wait(5);return False
        with patch('auth.password_valid',side_effect=slow):
            self.a.call('/');self.b.call('/')
            thread=threading.Thread(target=lambda:self.a.call('/login',{'username':'ian','password':'wrong','csrf':self.a.csrf}));thread.start()
            self.assertTrue(entered.wait(2));self.assertEqual(self.b.call('/login',{'username':'ian','password':'wrong','csrf':self.b.csrf})[0],429)
            release.set();thread.join()
        self.assertEqual(self.auth.failures['127.0.0.1'][0],1)
    def test_admin_revoke_reset_disable_remove_and_other_account_unchanged(self):
        self.a.login();self.b.login('other');self.auth.admin('revoke','ian')
        self.assertEqual(self.a.call('/api/conversations')[0],401);self.assertEqual(self.b.call('/api/conversations')[0],200)
        for change in ('reset','disable','remove'):
            self.records[0]['enabled']=True;self.write_accounts();self.a.login()
            if change=='reset':self.records[0]['version']='changed'
            elif change=='disable':self.records[0]['enabled']=False
            else:self.records.pop(0)
            self.write_accounts();self.assertEqual(self.a.call('/api/conversations')[0],401)
            self.assertEqual(self.b.call('/api/conversations')[0],200)
    def test_forwarding_approval_contract_no_bypass_and_no_bearer_leak(self):
        self.a.login();ident='12345678-1234-1234-1234-123456789abc'
        for decision in ('approve','reject'):
            body={'conversation_id':ident,'proposal_hash':'immutable-hash','decision':decision}
            self.assertEqual(self.a.call('/api/actions/'+ident+'/decision',body)[0],200)
            self.upstream.request.assert_called_with('POST','/actions/'+ident+'/decision',body)
        self.upstream.reset_mock()
        for path in ('/api/executions','/api/jobs','/api/http://evil'):
            self.assertEqual(self.a.call(path,{})[0],404)
        self.upstream.request.assert_not_called()
        self.upstream.request.return_value=(200,{'text':self.upstream.token})
        status,text,headers=self.a.call('/api/conversations');self.assertEqual(status,200);self.assertNotIn(self.upstream.token,text)
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
    def test_secure_cookie_https_setting(self):
        self.config['cookie_secure']=True
        self.config['allowed_origins']=['https://'+self.url.removeprefix('http://')]
        status,_,headers=self.a.call('/')
        self.assertEqual(status,200);self.assertIn('Secure',headers['Set-Cookie'])
    def test_malformed_account_configuration_fails_closed(self):
        self.a.login()
        self.accounts.write_text('{}')
        with self.assertRaises(ValueError):Auth(self.config)
        self.assertEqual(self.a.call('/api/conversations')[0],400)
        self.upstream.request.assert_not_called()
