#!/usr/bin/env python3
"""Independent HTTP clients, not physical browser/device acceptance.
Read ephemeral acceptance credentials from stdin, never arguments or logs.
"""
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
settings=json.load(sys.stdin);base=settings['base_url'];account=settings['username'];password=settings['password']
class BrowserHTTP:
    def __init__(self):
        self.jar=http.cookiejar.CookieJar();self.csrf=''
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(self.jar))
    def call(self,path,body=None,expected=200,csrf=True,origin=True):
        headers={}
        if body is not None:
            headers['Content-Type']='application/x-www-form-urlencoded' if path=='/login' else 'application/json'
            if csrf:headers['X-CSRF-Token']=self.csrf
            if origin:headers['Origin']=base
        data=(urllib.parse.urlencode(body).encode() if path=='/login' else json.dumps(body).encode()) if body is not None else None
        req=urllib.request.Request(base+path,data=data,headers=headers)
        try:
            with self.opener.open(req,timeout=20) as f:status,raw,kind=f.status,f.read(),f.headers.get_content_type()
        except urllib.error.HTTPError as e:status,raw,kind=e.code,e.read(),e.headers.get_content_type()
        assert status==expected,'Unexpected HTTP status for '+path+': '+str(status)
        text=raw.decode()
        assert settings.get('forbidden_bearer','\0') not in text,'Credential reflected to HTTP client'
        if kind=='application/json':return json.loads(text)
        match=re.search(r'name="csrf-token" content="([^"]+)"|name="csrf" value="([^"]+)"',text)
        if match:self.csrf=next(value for value in match.groups() if value)
        return text
    def login(self):
        self.call('/');self.call('/login',{'username':account,'password':password,'csrf':self.csrf})
a,b=BrowserHTTP(),BrowserHTTP()
a.call('/api/conversations',expected=401);a.login();b.login()
a.call('/api/conversations',{},expected=403,csrf=False)
a.call('/api/conversations',{},expected=403,origin=False)
conversation=a.call('/api/conversations',{},201)['id']
def send(client,text):
    message=client.call('/api/conversations/'+conversation+'/messages',{'request_id':str(uuid.uuid4()),'content':text},202)
    deadline=time.monotonic()+250
    while time.monotonic()<deadline:
        history=client.call('/api/conversations/'+conversation)
        user=next(m for m in history['messages'] if m['id']==message['id'])
        if user['status']!='processing':break
        time.sleep(1)
    else:raise RuntimeError('Conversation timed out')
    assert user['status']=='completed','Conversation did not complete: '+str(history['events'][-1].get('data',{}).get('message',''))
    replies=[m for m in history['messages'] if m.get('reply_to')==message['id']]
    assert len(replies)==1 and replies[0]['content'].strip() and not history['actions']
    assert not any(e['kind'] in ('diagnostic_execution','repair_execution') for e in history['events'])
    print(json.dumps({'user':text,'assistant':replies[0]['content']}),flush=True)
    return history
send(a,'I am naming a small garden robot Willow. In one short sentence, explain why that name suits a garden robot.')
history=send(b,'What name did we choose for the robot? Reply with just the name.')
assert 'willow' in history['messages'][-1]['content'].lower()
assert any(c['id']==conversation for c in b.call('/api/conversations')['conversations'])
a.call('/logout',{});a.call('/api/conversations',expected=401)
assert b.call('/api/conversations/'+conversation)==history
c=BrowserHTTP();c.login();assert c.call('/api/conversations/'+conversation)==history
print(json.dumps({'status':'PASS','conversation':conversation,'checks':['LAN HTTP password login','independent sessions','CSRF/Origin rejection','completed multi-turn conversation','reopened persisted history','logout isolation','no infrastructure actions']}))
