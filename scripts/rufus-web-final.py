#!/usr/bin/env python3
"""Single final controller script; no live repair or new guest is needed."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request
os.chdir('/opt/homelab-server-builds');os.environ['ANSIBLE_ROLES_PATH']=str(Path.cwd()/'Ansible/roles')
fd,name=tempfile.mkstemp(prefix='rufus-web-final-',suffix='.log');os.close(fd);log=Path(name)
def run(command):
    with log.open('a') as out:result=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
    if result.returncode:
        print(log.read_text()[-14000:]);raise SystemExit(result.returncode)
web_only=os.environ.get('RD_OPTION_SCOPE')=='web'
if web_only:
    run(['python3','-m','unittest','discover','-s','tests/rufus','-p','test_web.py','-v'])
else:
    run(['python3','scripts/validate.py'])
    run(['ansible-playbook','-i','Ansible/inventory/ai2.ini','--limit','rufus','--tags','rufus_application','Ansible/playbooks/rufus.yml'])
run(['ansible-playbook','-i','Ansible/inventory/ai2.ini','Ansible/playbooks/rufus-web.yml'])
token=subprocess.check_output(['python3','Rundeck/scripts/read-secret.py','RUNDECK_TOKEN'],text=True).strip()
def ids():
    req=urllib.request.Request('http://localhost:4440/api/50/project/HomeLab/executions?max=100',headers={'X-Rundeck-Auth-Token':token,'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as f:return {e['id'] for e in json.load(f)['executions']}
before=ids()
run(['ansible-playbook','-i','Ansible/inventory/ai2.ini','Ansible/playbooks/rufus-web-acceptance.yml']+(['--tags','web_isolation'] if web_only else []))
assert ids()==before,'Unexpected Rundeck execution during ordinary conversation'
print(json.dumps({'status':'PASS','scope':'web' if web_only else 'full','log':name,'checks':['web authentication tests','loopback isolation, file permissions and account separation']+([] if web_only else ['AI2 regressions','AI3 live chat/restart acceptance','zero Rundeck executions'])}))
for line in log.read_text().splitlines():
    if 'PASS' in line or 'assistant' in line:print(line)
