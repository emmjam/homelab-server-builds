#!/usr/bin/env python3
"""Single controller-side final validation/deployment/acceptance script."""
import json
from pathlib import Path
import os
import subprocess
import tempfile
import urllib.request

repo=Path('/opt/homelab-server-builds')
os.chdir(repo)
os.environ['ANSIBLE_ROLES_PATH']=str(repo/'Ansible/roles')
log=Path(tempfile.mkstemp(prefix='ai3-final-',suffix='.log')[1])
def run(args):
    with log.open('a') as out:
        result=subprocess.run(args,stdout=out,stderr=subprocess.STDOUT)
    if result.returncode:
        print(log.read_text()[-12000:]);raise SystemExit(result.returncode)
run(['python3','scripts/validate.py'])
run(['ansible-playbook','-i','Ansible/inventory/ai2.ini','--limit','rufus','--tags','rufus_application','Ansible/playbooks/rufus.yml'])
token=subprocess.check_output(['python3','Rundeck/scripts/read-secret.py','RUNDECK_TOKEN'],text=True).strip()
def ids():
    r=urllib.request.Request('http://localhost:4440/api/50/project/HomeLab/executions?max=100',
                             headers={'X-Rundeck-Auth-Token':token,'Accept':'application/json'})
    with urllib.request.urlopen(r,timeout=15) as f:return {e['id'] for e in json.load(f)['executions']}
before=ids()
run(['ansible-playbook','-i','Ansible/inventory/ai2.ini','Ansible/playbooks/ai3-acceptance.yml'])
assert ids()==before,'Rundeck execution list changed during ordinary chat acceptance'
print(json.dumps({'status':'PASS','log':str(log),'checks':['automated suite including AI2 regression','local multi-turn chat','durable assistant replies','history and context after restart','zero Rundeck executions during chat']}))
print(log.read_text()[-9000:])
