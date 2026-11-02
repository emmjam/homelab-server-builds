#!/usr/bin/env python3
"""Live API proof as Rufus; no power transitions, model generation or repairs."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import urllib.error
import urllib.request
sys.path.insert(0,'/opt/rufus/app')
from config import load
from nodes import Nodes
config=load('/opt/rufus/config/config.json')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def call(path,body=None,auth=True,expected=200):
    request=urllib.request.Request('http://127.0.0.1:8787'+path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+config['api_token']} if auth else {})
    try:
        with opener.open(request,timeout=10) as response:status,data=response.status,json.load(response)
    except urllib.error.HTTPError as error:status,data=error.code,json.load(error)
    assert status==expected,(path,status,data)
    return data
with sqlite3.connect('file:'+config['database']+'?mode=ro',uri=True) as db:baseline=db.execute('SELECT count(*) FROM executions').fetchone()[0]
call('/nodes',auth=False,expected=401)
snapshot=call('/nodes');assert {n['id'] for n in snapshot['nodes']}=={'tnas','ai-agent','ai-worker','server1','server2'}
for node in snapshot['nodes']:
    assert not node['stale']
    assert call('/nodes/'+node['id'])['id']==node['id']
    capabilities=node['last_verified_capabilities']
    if node['last_success_at']:
        assert capabilities['hardware']['cpu']['model'] and capabilities['hardware']['ram_bytes']>0
        assert capabilities['hardware']['storage']
    if node['id'] in ('server1','server2'):
        assert node['known_capabilities']['os']['version']=='20.04'
        assert node['known_capabilities']['os']['verified_at'] is None
    print(json.dumps({'node':node['id'],'state':node['observation']['state'],'last_success_at':node['last_success_at'],
        'cpu':capabilities['hardware']['cpu'] if capabilities else None,
        'ram_bytes':capabilities['hardware']['ram_bytes'] if capabilities else None,
        'root_available_bytes':next((d['available_bytes'] for d in capabilities['hardware']['storage'] if d['mount']=='/'),None) if capabilities else None,
        'os':capabilities['os'] if capabilities else node['known_capabilities']['os'],
        'ollama':capabilities['runtimes']['ollama'] if capabilities else None}),flush=True)
# A trusted snapshot reader with a controlled clock proves expiry without changing
# production clocks/files or waiting for the real freshness interval.
future=snapshot['received_at']+snapshot['stale_seconds']+1
expired=Nodes(clock=lambda:future).get()
assert all(n['stale'] and n['observation']['state']=='stale' and n['observation']['metrics'] is None for n in expired['nodes'])
assert [n['last_success_at'] for n in expired['nodes']]==[n['last_success_at'] for n in snapshot['nodes']]
assert not os.access('/var/lib/rufus-discovery/status',os.W_OK)
call('/nodes',{'command':'echo forbidden'},expected=404)
call('/nodes/ai-agent/refresh',{},expected=404)
call('/nodes/not-a-node',expected=404)
with sqlite3.connect('file:'+config['database']+'?mode=ro',uri=True) as db:assert db.execute('SELECT count(*) FROM executions').fetchone()[0]==baseline
print('PASS five-node API; sourced hardware; models; stale expiry; authenticated read-only access; no infrastructure execution',flush=True)
