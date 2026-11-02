#!/usr/bin/env python3
"""Single SSH entry point: relevant tests, Ansible deployment and passive proof."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
if os.geteuid()!=0:raise SystemExit('Run through the existing controller administrator sudo context')
repo=Path('/opt/homelab-server-builds');os.chdir(repo)
os.environ['ANSIBLE_ROLES_PATH']=str(repo/'Ansible/roles')
fd,name=tempfile.mkstemp(prefix='node-discovery-final-',suffix='.log');os.close(fd)
def run(args,input=None):
    with open(name,'a') as out:r=subprocess.run(args,input=input,text=True,stdout=out,stderr=subprocess.STDOUT)
    if r.returncode:
        print('FAIL log '+name);print(Path(name).read_text()[-18000:]);raise SystemExit(r.returncode)
run(['python3','-m','unittest','discover','-s','tests/rufus','-v'])
run(['ansible-playbook','-i','Ansible/inventory/ai2.ini','--limit','rufus','--tags','rufus_application','Ansible/playbooks/rufus.yml'])
run(['ansible-playbook','-i','Ansible/inventory/ai-inference.ini','-i','Ansible/inventory/ai2.ini','-i','Ansible/inventory/compute.yml','Ansible/playbooks/node-discovery.yml'])
run(['sudo','-n','systemctl','start','rufus-discovery.service'])
run(['sudo','-n','systemctl','is-enabled','--quiet','rufus-discovery.timer'])
run(['ssh','-i','/var/lib/rundeck/.ssh/target_ed25519','-o','BatchMode=yes','-o','HostKeyAlias=rufus',
     '-o','UserKnownHostsFile=/var/lib/rundeck/.ssh/managed_debian_known_hosts','-o','StrictHostKeyChecking=yes','rundeck@rufus.lan',
     'sudo -n runuser -u rufus -- /opt/rufus/venv/bin/python -'],input=Path('scripts/node-discovery-acceptance.py').read_text())
print('PASS Task 2 passive discovery; log '+name)
for line in Path(name).read_text().splitlines():
    if line.startswith(('PASS','Ran ','OK','{"node"')):print(line)
