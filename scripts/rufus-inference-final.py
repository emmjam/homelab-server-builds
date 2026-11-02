#!/usr/bin/env python3
"""One SSH entry point for focused regression, Ansible deployment and live proof."""
import os
from pathlib import Path
import subprocess
import tempfile
repo=Path('/opt/homelab-server-builds');os.chdir(repo)
os.environ['ANSIBLE_ROLES_PATH']=str(repo/'Ansible/roles')
fd,name=tempfile.mkstemp(prefix='rufus-inference-final-',suffix='.log');os.close(fd)
def run(args,input=None):
    with open(name,'a') as out:result=subprocess.run(args,input=input,text=True,stdout=out,stderr=subprocess.STDOUT)
    if result.returncode:
        print(Path(name).read_text()[-16000:]);raise SystemExit(result.returncode)
run(['python3','-m','unittest','discover','-s','tests/rufus','-v'])
run(['ansible-playbook','-i','Ansible/inventory/ai2.ini','--limit','rufus','--tags','rufus_application','Ansible/playbooks/rufus.yml'])
run(['ansible-playbook','-i','Ansible/inventory/ai-inference.ini','--limit','rufus_inference','--tags','rufus_inference_client','Ansible/playbooks/ai-inference.yml'])
run(['ssh','-i','/var/lib/rundeck/.ssh/target_ed25519','-o','BatchMode=yes','-o','HostKeyAlias=rufus',
    '-o','UserKnownHostsFile=/var/lib/rundeck/.ssh/managed_debian_known_hosts','-o','StrictHostKeyChecking=yes',
    'rundeck@rufus.lan','sudo -n runuser -u rufus -- /opt/rufus/venv/bin/python -'],
    input=Path('scripts/rufus-inference-acceptance.py').read_text())
print('PASS focused inference deployment and acceptance; log '+name)
for line in Path(name).read_text().splitlines():
    if line.startswith(('Ran ','OK','PASS','{')):print(line)
