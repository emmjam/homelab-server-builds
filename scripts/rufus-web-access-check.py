#!/usr/bin/env python3
"""Laptop-side HTTP acceptance via one SSH transport to the trusted controller.

This administrative test helper is not part of normal browser access. It keeps
all API/Rundeck credentials on their existing hosts and never prints login codes.
"""
import argparse
import http.cookiejar
import json
import shlex
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

REMOTE=r'''
import json,socket,subprocess,sys,time,urllib.request
repo='/opt/homelab-server-builds'
key=['sudo','-n','-u','rundeck','ssh','-i','/var/lib/rundeck/.ssh/target_ed25519','-o','BatchMode=yes','-o','HostKeyAlias=rufus','-o','UserKnownHostsFile=/var/lib/rundeck/.ssh/managed_debian_known_hosts','-o','StrictHostKeyChecking=yes']
forward=subprocess.Popen(key+['-o','ExitOnForwardFailure=yes','-N','-L','127.0.0.1:18788:127.0.0.1:8788','rundeck@rufus.lan'])
def code():return subprocess.check_output(key+['rundeck@rufus.lan','sudo -n -u rufus-web python3 /opt/rufus-web/app/web.py --login-code'],text=True).strip()
token=subprocess.check_output(['python3',repo+'/Rundeck/scripts/read-secret.py','RUNDECK_TOKEN'],text=True).strip()
def ids():
 req=urllib.request.Request('http://localhost:4440/api/50/project/HomeLab/executions?max=100',headers={'X-Rundeck-Auth-Token':token,'Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=15) as f:return {e['id'] for e in json.load(f)['executions']}
try:
 for _ in range(50):
  if forward.poll() is not None:raise RuntimeError('Controller forward failed')
  try:
   with socket.create_connection(('127.0.0.1',18788),timeout=1):break
  except OSError:time.sleep(.1)
 else:raise RuntimeError('Controller forward unavailable')
 for port in (8787,8788):
  try:connection=socket.create_connection(('rufus.lan',port),timeout=3)
  except OSError:pass
  else:connection.close();raise RuntimeError('LAN listener unexpectedly reachable')
 baseline=ids();print(json.dumps({'code':code(),'status':'ready'}),flush=True)
 for command in sys.stdin:
  if command.strip()=='CODE':print(json.dumps({'code':code()}),flush=True)
  elif command.strip()=='CHECK':
   assert ids()==baseline,'Unexpected Rundeck execution during ordinary web chat'
   print(json.dumps({'status':'PASS','check':'zero Rundeck executions; controller LAN access denied'}),flush=True)
  elif command.strip()=='QUIT':break
finally:
 forward.terminate();forward.wait()
'''
parser=argparse.ArgumentParser();parser.add_argument('--controller',default='rundeck');parser.add_argument('--port',type=int,default=8877);args=parser.parse_args()
transport=subprocess.Popen(['ssh','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-L',f'127.0.0.1:{args.port}:127.0.0.1:18788',args.controller,'python3 -u -c '+shlex.quote(REMOTE)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
base='http://127.0.0.1:'+str(args.port)
def control(command):
 transport.stdin.write(command+'\n');transport.stdin.flush()
 line=transport.stdout.readline()
 if not line:raise RuntimeError('SSH acceptance transport closed')
 return json.loads(line)
def opener():return urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
client=opener()
def call(path,body=None,expect=200,form=False,origin=True):
 headers={}
 if body is not None:
  headers['Content-Type']='application/x-www-form-urlencoded' if form else 'application/json'
  if origin:headers['Origin']=base
 request=urllib.request.Request(base+path,data=(urllib.parse.urlencode(body).encode() if form else json.dumps(body).encode()) if body is not None else None,headers=headers)
 try:
  with client.open(request,timeout=20) as response:
   raw=response.read();status=response.status;response_headers=response.headers
 except urllib.error.HTTPError as error:raw=error.read();status=error.code;response_headers=error.headers
 assert status==expect,(path,status,raw[:500])
 return json.loads(raw) if response_headers.get_content_type()=='application/json' else raw.decode()
def message(conversation,text):
 request=call('/api/conversations/'+conversation+'/messages',{'request_id':str(uuid.uuid4()),'content':text},202)
 deadline=time.monotonic()+240
 while time.monotonic()<deadline:
  history=call('/api/conversations/'+conversation)
  user=next(m for m in history['messages'] if m['id']==request['id'])
  if user['status']!='processing':break
  time.sleep(1)
 else:raise RuntimeError('Web conversation timed out')
 assert user['status']=='completed',history['events'][-2:]
 replies=[m for m in history['messages'] if m.get('reply_to')==request['id']]
 assert len(replies)==1 and not history['actions']
 print(json.dumps({'user':text,'assistant':replies[0]['content']}),flush=True)
 return history
try:
 ready=json.loads(transport.stdout.readline());assert ready['status']=='ready'
 for port in (8787,8788):
  try:connection=socket.create_connection(('rufus.lan',port),timeout=3)
  except OSError:pass
  else:connection.close();raise RuntimeError('Laptop reached a direct LAN listener')
 call('/api/conversations',expect=401)
 assert 'Sign-in code' in call('/')
 call('/login',{'code':ready['code']},form=True)
 call('/api/conversations',{},403,origin=False)
 conversation=call('/api/conversations',{},201)['id']
 message(conversation,'I am naming a small garden robot Willow. In one short sentence, explain why that name suits a garden robot.')
 history=message(conversation,'What name did we choose for the robot? Reply with just the name.')
 assert 'willow' in history['messages'][-1]['content'].casefold()
 assert any(c['id']==conversation for c in call('/api/conversations')['conversations'])
 call('/logout',{})
 call('/api/conversations',expect=401)
 client=opener();fresh=control('CODE')
 call('/login',{'code':fresh['code']},form=True)
 assert call('/api/conversations/'+conversation)==history,'Reopened history changed'
 assert 'localStorage' not in call('/app.js') and 'Bearer' not in call('/app.js')
 result=control('CHECK');assert result['status']=='PASS'
 print(json.dumps({'status':'PASS','conversation':conversation,'checks':['SSH tunnel login from laptop','ordinary multi-turn web chat','reopen history in a new session','unauthenticated and cross-origin access denied','direct API and web LAN access denied from laptop and controller','zero Rundeck executions']}),flush=True)
finally:
 if transport.poll() is None:
  try:control('QUIT')
  except Exception:pass
  try:transport.wait(timeout=10)
  except subprocess.TimeoutExpired:transport.terminate();transport.wait()
