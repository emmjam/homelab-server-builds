#!/usr/bin/env python3
"""Run inside Rufus as its service user; never print or accept secret values."""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import uuid

sys.path.insert(0,'/opt/rufus/app')
from config import load

config=load('/opt/rufus/config/config.json')
state_file=Path('/opt/rufus/data/ai2-acceptance.json')
state=json.loads(state_file.read_text()) if state_file.exists() else {}
base='http://127.0.0.1:'+str(config.get('port',8787))
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def call(path,body=None,expected=200):
    request=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+config['api_token'],'Content-Type':'application/json'})
    try:
        with opener.open(request,timeout=15) as response:
            assert response.status==expected
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code!=expected: raise RuntimeError('Unexpected Rufus HTTP status '+str(error.code)) from None
        return json.load(error)

def save(): state_file.write_text(json.dumps(state,indent=2)+'\n')
parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['propose','reject','approve','status','boundaries'])
parser.add_argument('--action');parser.add_argument('--hash');args=parser.parse_args()
if args.stage=='propose':
    conversation=call('/conversations',{},201)['id']
    call('/conversations/'+conversation+'/messages',{'request_id':str(uuid.uuid4()),
        'content':'The isolated disposable APT cache fixture is unavailable. Diagnose it and propose the supported restart repair for the fixture only.'},202)
    deadline=time.monotonic()+180
    while True:
        history=call('/conversations/'+conversation)
        if history['actions']:break
        if history['messages'] and history['messages'][-1]['status']!='processing':
            print(json.dumps({'status':'FAIL','history':history}));raise SystemExit(1)
        if time.monotonic()>deadline:raise SystemExit('Conversation timed out; inspect persisted history')
        time.sleep(1)
    action=history['actions'][-1];state.update(conversation=conversation,action=action['id'],hash=action['proposal_hash']);save()
    assert action['status']=='pending' and action['execution_id'] is None
    print(json.dumps({'status':'APPROVAL_REQUIRED','action':action,'evidence':[e for e in history['events'] if e['kind']=='evidence']}))
elif args.stage=='reject':
    action=call('/actions/'+state['action']+'/decision',{'conversation_id':state['conversation'],
        'proposal_hash':state['hash'],'decision':'reject'},202)
    assert action['status']=='rejected' and action['execution_id'] is None
    print(json.dumps({'status':'PASS','check':'rejected proposal has no execution','action_id':state['action']}))
elif args.stage=='approve':
    if args.action!=state['action'] or args.hash!=state['hash']:raise SystemExit('Exact action/hash arguments are required')
    action=call('/actions/'+state['action']+'/decision',{'conversation_id':state['conversation'],
        'proposal_hash':state['hash'],'decision':'approve'},202)
    print(json.dumps({'status':action['status'],'action_id':action['id']}))
elif args.stage=='status':
    deadline=time.monotonic()+180
    while True:
        action=call('/actions/'+state['action'])
        if action['status'] not in ('approved','submitting','running','verification_submitting','verifying'):break
        if time.monotonic()>deadline:break
        time.sleep(1)
    print(json.dumps({'action':action,'history':call('/conversations/'+state['conversation'])}))
else:
    call('/executions',{'operation':'delete-vm','options':{}},403)
    call('/executions',{'operation':'fixture-restart','options':{}},403)
    job='4eb507e0-9514-4cf2-babc-347df5faf73c'
    request=urllib.request.Request(config['rundeck_url'].rstrip('/')+'/api/50/job/'+job+'/run',
        data=b'{"options":{}}',headers={'X-Rundeck-Auth-Token':config['token'],'Content-Type':'application/json'})
    try:
        with opener.open(request,timeout=10):raise RuntimeError('Unapproved Rundeck mutation was accepted')
    except urllib.error.HTTPError as error:
        assert error.code==403,'Expected independent Rundeck denial'
    print(json.dumps({'status':'PASS','checks':['Rufus unapproved operation denied','Rufus direct mutation bypass denied','Rundeck unapproved operation independently denied']}))
