#!/usr/bin/env python3
"""Run as Rufus: ordinary local chat acceptance before/after a managed restart."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import urllib.request
import uuid

sys.path.insert(0,'/opt/rufus/app')
from config import load
config=load('/opt/rufus/config/config.json')
state_path=Path('/opt/rufus/data/ai3-acceptance.json')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def call(path,body=None):
    request=urllib.request.Request('http://127.0.0.1:'+str(config.get('port',8787))+path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+config['api_token'],'Content-Type':'application/json'})
    with opener.open(request,timeout=15) as response:return json.load(response)
def fingerprint(history):return hashlib.sha256(json.dumps(history,sort_keys=True).encode()).hexdigest()
def executions():
    with sqlite3.connect('file:'+config['database']+'?mode=ro',uri=True) as db:
        return db.execute('SELECT count(*) FROM executions').fetchone()[0]
def send(conversation,text):
    message=call('/conversations/'+conversation+'/messages',{'request_id':str(uuid.uuid4()),'content':text})
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        history=call('/conversations/'+conversation)
        user=next(m for m in history['messages'] if m['id']==message['id'])
        if user['status']!='processing':break
        time.sleep(1)
    else:raise RuntimeError('Conversation timed out')
    assert user['status']=='completed',json.dumps(history['events'][-2:])
    replies=[m for m in history['messages'] if m.get('reply_to')==message['id']]
    assert len(replies)==1 and replies[0]['content'].strip(),'Missing durable assistant reply'
    assert not history['actions'] and not any(e['kind'] in ('diagnostic_execution','repair_execution') for e in history['events'])
    print(json.dumps({'user':text,'assistant':replies[0]['content']}),flush=True)
    return history,replies[0]['content']
parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['before','after']);args=parser.parse_args()
if args.stage=='before':
    baseline=executions();conversation=call('/conversations',{})['id']
    send(conversation,'Reply with exactly these two words: Amber Willow')
    history,answer=send(conversation,'What was the second word in your previous reply? Reply with that word only.')
    assert answer.strip().strip('.!\"').casefold()=='willow','Assistant did not use conversational context'
    assert executions()==baseline,'Ordinary chat submitted an execution'
    state_path.write_text(json.dumps({'conversation':conversation,'fingerprint':fingerprint(history),'executions':baseline})+'\n')
    print('PASS local multi-turn conversation; zero Rufus executions',flush=True)
else:
    state=json.loads(state_path.read_text());history=call('/conversations/'+state['conversation'])
    assert fingerprint(history)==state['fingerprint'],'History changed across restart'
    _,answer=send(state['conversation'],'Which word did you give in your last answer? Reply with that word only.')
    assert answer.strip().strip('.!\"').casefold()=='willow','Post-restart context missing'
    assert executions()==state['executions'],'Ordinary chat submitted an execution'
    print('PASS history and context survive service restart; zero Rufus executions',flush=True)
