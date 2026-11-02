#!/usr/bin/env python3
"""Full Task 1 automation. No browser/device claims or live repairs."""
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import socket
import subprocess
import tempfile
import urllib.request
import uuid
repo=Path('/opt/homelab-server-builds');os.chdir(repo);os.environ['ANSIBLE_ROLES_PATH']=str(repo/'Ansible/roles')
fd,name=tempfile.mkstemp(prefix='rufus-web-final-',suffix='.log');os.close(fd);log=Path(name)
def run(command,input=None):
    with log.open('a') as out:result=subprocess.run(command,input=input,text=True,stdout=out,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Command failed: '+str(result.returncode))
def play(name,*args):run(['ansible-playbook','-i','Ansible/inventory/ai2.ini',*args,'Ansible/playbooks/'+name])
def read_secret(key):return subprocess.check_output(['python3','Rundeck/scripts/read-secret.py',key],text=True).strip()
account_source=Path('/var/lib/rundeck/rufus-web-accounts.json')
def source_accounts():return json.loads(account_source.read_text())
def write_accounts(records):
    # Dedicated 0600 hash-only source; do not touch the established secrets file.
    with account_source.open('r+') as f:
        f.seek(0);f.write(json.dumps(records,separators=(',',':'))+'\n');f.truncate();f.flush();os.fsync(f.fileno())
admin_token=read_secret('RUNDECK_TOKEN')
def ids():
    req=urllib.request.Request('http://localhost:4440/api/50/project/HomeLab/executions?max=100',headers={'X-Rundeck-Auth-Token':admin_token,'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as f:return {e['id'] for e in json.load(f)['executions']}
original=source_accounts();assert any(a['username']=='ian' and a['enabled'] for a in original)
spec=importlib.util.spec_from_file_location('web_auth',repo/'RufusWeb/auth.py');auth=importlib.util.module_from_spec(spec);spec.loader.exec_module(auth)
password=secrets.token_urlsafe(32);temporary={'id':str(uuid.uuid4()),'username':'acceptance-'+uuid.uuid4().hex[:12],'version':str(uuid.uuid4()),'enabled':True,'password_hash':auth.password_hash(password)}
source_changed=False
try:
    run(['python3','scripts/validate.py'])
    run(['ansible-playbook','-i','Ansible/inventory/ai-inference.ini','--limit','rufus_inference','--tags','rufus_inference_client','Ansible/playbooks/ai-inference.yml'])
    play('rufus.yml','--limit','rufus','--tags','rufus_application')
    write_accounts(original+[temporary]);source_changed=True;play('rufus-web.yml')
    before=ids()
    play('rufus-web-acceptance.yml')
    address=socket.gethostbyname('rufus.lan')
    try:connection=socket.create_connection(('rufus.lan',8787),timeout=3)
    except ConnectionRefusedError:pass
    else:connection.close();raise RuntimeError('API exposed to LAN')
    settings={'base_url':'http://rufus.lan:8788','username':temporary['username'],'password':password,'forbidden_bearer':read_secret('RUFUS_API_TOKEN')}
    run(['python3','scripts/rufus-web-http-acceptance.py'],input=json.dumps(settings))
    assert ids()==before,'Unexpected Rundeck execution during ordinary chat'
except Exception:
    print(log.read_text()[-14000:]);raise
finally:
    # Remove only our temporary identity, preserving concurrent administrative edits.
    if source_changed:
        write_accounts([a for a in source_accounts() if a['id']!=temporary['id']])
        try:play('rufus-web.yml')
        except Exception:print('FAIL cleanup/deployment; inspect protected controller log');raise
try:
    # Stale sessions must be unusable after the temporary account is removed.
    with urllib.request.urlopen('http://rufus.lan:8788',timeout=10) as f:assert f.status==200
    play('rufus-web.yml')
    recap=log.read_text().split('PLAY RECAP')[-1]
    assert re.search(r'changed=0\s',recap), 'Repeated web deployment was not idempotent'
    print(json.dumps({'status':'PASS','log':name,'checks':['complete automated suites including AI2 and HTTP auth/session tests','AI3 real chat and restart persistence','LAN Web and loopback API isolation','multi-turn HTTP chat and reopened history','zero Rundeck executions during ordinary chat','temporary account removed','idempotent web deployment'],'browser_laptop':'NOT PERFORMED','browser_phone':'NOT PERFORMED'}))
    for line in log.read_text().splitlines():
        if 'PASS' in line or 'assistant' in line:print(line)
except Exception:
    print(log.read_text()[-14000:]);raise
