"""Browser authentication, restricted forwarding and existing approval contracts."""
import http.cookiejar
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'RufusWeb'))
from web import Sessions,handler,allowed


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.now=1000;self.sessions=Sessions(self.temp.name+'/db',lambda:self.now)
        self.client=Mock();self.client.token='server-only-bearer'
        self.client.request.return_value=(200,{'conversations':[]})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler({},self.sessions,self.client))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.cookies=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(self.cookies))
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,path,body=None,origin=True,host=None):
        headers={}
        if body is not None and origin:headers['Origin']=self.url
        if host:headers['Host']=host
        data=(body.encode() if isinstance(body,str) else json.dumps(body).encode()) if body is not None else None
        r=urllib.request.Request(self.url+path,data=data,headers=headers)
        try:
            with self.opener.open(r) as f:return f.status,f.read(),f.headers
        except urllib.error.HTTPError as e:return e.code,e.read(),e.headers
    def login(self):return self.request('/login',urllib.parse.urlencode({'code':self.sessions.code()}))
    def test_no_unauthenticated_proxy(self):
        self.assertEqual(self.request('/api/conversations')[0],401)
        self.client.request.assert_not_called()
        status,body,headers=self.request('/')
        self.assertEqual(status,200);self.assertIn(b'Sign-in code',body)
        self.assertNotIn(self.client.token.encode(),body)
    def test_one_use_expiring_codes_and_hashed_storage(self):
        code=self.sessions.code();token=self.sessions.login(code)
        self.assertTrue(self.sessions.valid(token));self.assertIsNone(self.sessions.login(code))
        with self.sessions.db() as db:
            self.assertNotEqual(db.execute('select hash from sessions').fetchone()[0],token)
        code=self.sessions.code();self.now+=181;self.assertIsNone(self.sessions.login(code))
        self.now+=28800;self.assertFalse(self.sessions.valid(token))
    def test_cookie_attributes_and_logout(self):
        code=self.sessions.code()
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args):return None
        opener=urllib.request.build_opener(NoRedirect())
        req=urllib.request.Request(self.url+'/login',data=urllib.parse.urlencode({'code':code}).encode(),headers={'Origin':self.url})
        with self.assertRaises(urllib.error.HTTPError) as caught:opener.open(req)
        header=caught.exception.headers['Set-Cookie']
        self.assertIn('HttpOnly',header);self.assertIn('SameSite=Strict',header)
        self.login();self.assertEqual(self.request('/api/conversations')[0],200)
        self.assertEqual(self.request('/logout',{})[0],200)
        self.assertEqual(self.request('/api/conversations')[0],401)
    def test_cross_origin_and_dns_rebinding_blocked(self):
        self.login()
        self.assertEqual(self.request('/api/conversations',{},origin=False)[0],403)
        self.assertEqual(self.request('/api/conversations',host='evil.example:1234')[0],403)
        self.client.request.assert_not_called()
    def test_conversation_and_exact_approval_rejection_forwarding(self):
        self.login();ident='a'*8+'-'+ 'b'*4+'-'+ 'c'*4+'-'+ 'd'*4+'-'+ 'e'*12
        for decision in ('approve','reject'):
            body={'conversation_id':ident,'proposal_hash':'exact-hash','decision':decision}
            self.request('/api/actions/'+ident+'/decision',body)
            self.client.request.assert_called_with('POST','/actions/'+ident+'/decision',body)
        body={'request_id':ident,'content':'Hello'}
        self.request('/api/conversations/'+ident+'/messages',body)
        self.client.request.assert_called_with('POST','/conversations/'+ident+'/messages',body)
    def test_no_arbitrary_proxy_or_execution_bypass(self):
        self.login()
        for path in ('/api/executions','/api/jobs','/api/http://evil','/api/conversations?secret=x'):
            self.assertEqual(self.request(path,{})[0],404)
        self.client.request.assert_not_called()
    def test_bearer_not_exposed_even_if_upstream_reflects_it(self):
        self.login();self.client.request.return_value=(200,{'text':self.client.token})
        status,body,_=self.request('/api/conversations')
        self.assertEqual(status,200);self.assertNotIn(self.client.token.encode(),body)
    def test_restart_preserves_sessions(self):
        token=self.sessions.login(self.sessions.code())
        reopened=Sessions(self.sessions.database,lambda:self.now)
        self.assertTrue(reopened.valid(token))
    def test_page_security_headers_and_text_only_rendering(self):
        self.login();status,body,headers=self.request('/')
        self.assertEqual(status,200);self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
        self.assertEqual(headers['Cache-Control'],'no-store')
        source=(Path(__file__).resolve().parents[2]/'RufusWeb/static/app.js').read_text()
        self.assertNotIn('innerHTML',source);self.assertNotIn('localStorage',source);self.assertNotIn('Bearer',source)
