#!/usr/bin/env python3
"""Run on Rundeck as administrator: scoped Ansible deploy and combined acceptance.

Working snapshot only; never Git refresh, provision hosts or execute repairs.
Stdout is a protocol for run-rufus-vscode-deployment.py. One auth event contains
an ephemeral credential: the runner consumes it privately and never logs it.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
SSH=['sudo','-u','rundeck','ssh','-i','/var/lib/rundeck/.ssh/target_ed25519',
     '-o','BatchMode=yes','-o','ConnectTimeout=10','-o','HostKeyAlias=rufus',
     '-o','UserKnownHostsFile=/var/lib/rundeck/.ssh/managed_debian_known_hosts',
     '-o','StrictHostKeyChecking=yes','rundeck@rufus.lan']

def emit(check,**data):print(json.dumps(dict(check=check,**data)),flush=True)

def remote(code,as_rufus=False):
    command=['sudo','-n']+(['runuser','-u','rufus','--'] if as_rufus else [])+['python3','-c',code]
    raw=subprocess.check_output(SSH+[shlex.join(command)],timeout=450,text=True)
    return json.loads(raw)


def main():
    sys.path.insert(0,str(ROOT/'RufusWeb'))
    from auth import password_hash
    manifest=json.loads((ROOT/'DEPLOYMENT-SOURCE.json').read_text())
    for name,expected in manifest['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
    log=Path(tempfile.mkstemp(prefix='rufus-vscode-deploy-',suffix='.log')[1])
    log.chmod(0o600)
    emit('source-verified',source=str(ROOT),base_commit=manifest['base_commit'],log=str(log))
    def command(args):
        with log.open('a') as output:
            subprocess.run(args,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,check=True,timeout=600,
                           env={**os.environ,"ANSIBLE_CONFIG":str(ROOT/"Ansible/ansible.cfg"),
                                "ANSIBLE_ROLES_PATH":str(ROOT/"Ansible/roles")})
    def deploy_web():command(['ansible-playbook','-i','Ansible/inventory/ai2.ini','Ansible/playbooks/rufus-web.yml'])
    baseline=remote('''import json,sqlite3,pathlib,subprocess,time
p=pathlib.Path('/opt/rufus/config/config.json');c=json.loads(p.read_text());db=sqlite3.connect(c['database'])
assert db.execute("SELECT count(*) FROM messages WHERE status='processing'").fetchone()[0]==0,'Active conversation: defer deployment'
assert db.execute("SELECT count(*) FROM actions WHERE status IN ('approved','submitting','running','verifying','verification_submitting')").fetchone()[0]==0,'Active operation: defer deployment'
b=pathlib.Path('/var/backups/rufus-vscode-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()));b.mkdir(mode=0o700)
with sqlite3.connect(b/'executions.sqlite3') as dest:db.backup(dest)
subprocess.run(['tar','-czf',str(b/'application-config.tgz'),'-C','/','opt/rufus/app','opt/rufus/config','opt/rufus-web/app','opt/rufus-web/config'],check=True,stderr=subprocess.DEVNULL)
print(json.dumps({'executions':db.execute('SELECT count(*) FROM executions').fetchone()[0],'backup':str(b),'conversations':db.execute('SELECT count(*) FROM conversations').fetchone()[0]}))''')
    # Prevent the application playbook from replacing a divergent live policy.
    for name,destination in [('policy.json','policy.json'),('catalogue.json','catalogue.json')]:
        actual=remote("import hashlib,json;print(json.dumps(hashlib.sha256(open('/opt/rufus/config/"+destination+"','rb').read()).hexdigest()))")
        assert actual==hashlib.sha256((ROOT/'Rufus'/name).read_bytes()).hexdigest(),'Live policy differs; review before deployment'
    emit('quiescent-preflight-and-protected-backup',**baseline)
    command(['ansible-playbook','-i','Ansible/inventory/ai2.ini','Ansible/playbooks/rufus.yml','--tags','rufus_application'])
    emit('application-deployed')
    command(['ansible-playbook','-i','Ansible/inventory/ai-inference.ini','Ansible/playbooks/ai-inference.yml','--limit','rufus_inference','--tags','rufus_inference_client'])
    emit('inference-client-and-budget-config-deployed')
    source=Path('/var/lib/rundeck/rufus-web-accounts.json')
    original=source.read_bytes();metadata=source.stat();account='vscode-acceptance-'+secrets.token_hex(4);password=secrets.token_urlsafe(32)
    records=json.loads(original);records.append({'id':account,'username':account,'enabled':True,'version':'1','password_hash':password_hash(password)})
    try:
        source.write_text(json.dumps(records));deploy_web()
        emit('gateway-deployed')
        # Source equality proves uncommitted snapshot deployment, not Git publication.
        expected={}
        for name in ['app.py','config.py','rundeck.py','inference.py','conversations.py','budget.py','workflow.py','nodes.py']:
            expected['/opt/rufus/app/'+name]=hashlib.sha256((ROOT/'Rufus'/name).read_bytes()).hexdigest()
        for name in ['web.py','auth.py','static/index.html','static/login.html','static/app.js','static/style.css']:
            expected['/opt/rufus-web/app/'+name]=hashlib.sha256((ROOT/'RufusWeb'/name).read_bytes()).hexdigest()
        state=remote('''import hashlib,json,subprocess
expected='''+repr(expected)+'''
assert all(hashlib.sha256(open(p,'rb').read()).hexdigest()==h for p,h in expected.items()),'Deployed source mismatch'
subprocess.run(['systemctl','is-active','--quiet','rufus','rufus-web'],check=True)
c=json.load(open('/opt/rufus/config/inference.json'))
assert c['incoming_message_tokens']==4096 and c['history_context_tokens']==2048 and c['repository_context_tokens']==1536
raw=subprocess.check_output(['journalctl','-u','rufus','-u','rufus-web','--since','5 minutes ago','--no-pager','-p','err'],text=True)
print(json.dumps({'modules_verified':len(expected),'services':'active','budget_config':'verified','recent_error_log_lines':len([x for x in raw.splitlines() if x and x!='-- No entries --'])}))''')
        emit('deployed-source-services-config-and-logs',**state)
        emit('auth',url='http://rufus.lan:8788',username=account,password=password)
        # EOF/runner failure always enters finally and restores existing accounts.
        result=json.loads(sys.stdin.readline())
        assert result.get('status')=='PASS','Local extension transport acceptance failed; see local diagnostic log'
        emit('local-extension-transport-live-acceptance-passed')
        inference=remote('''import sys,json,http.client
sys.path.insert(0,'/opt/rufus/app')
from config import load
from inference import Client,InferenceError
c=load('/opt/rufus/config/config.json')['inference'];c={**c,'chat_num_predict':1}
original=http.client.HTTPConnection;observed={}
class Capture(original):
 def getresponse(self):
  response=super().getresponse();read=response.read
  def capture(*args):
   raw=read(*args);r=json.loads(raw);observed.update({k:r.get(k) for k in ('done','done_reason','prompt_eval_count','eval_count')});return raw
  response.read=capture;return response
http.client.HTTPConnection=Capture
try:Client(c).chat([{'role':'user','content':'Write a detailed explanation of how a fictional garden grows.'}]);raise AssertionError('Expected incomplete-response rejection')
except InferenceError as e:
 assert e.details.get('code')=='inference_incomplete',str(e)
 print(json.dumps({'incomplete_detected':True,'code':e.details['code'],'ollama':observed}))''',as_rufus=True)
        emit('real-ollama-output-exhaustion-rejected',**inference)
    finally:
        source.write_bytes(original);deploy_web()
        restored=source.stat()
        assert source.read_bytes()==original and (restored.st_uid,restored.st_gid,restored.st_mode)==(metadata.st_uid,metadata.st_gid,metadata.st_mode)
        emit('original-accounts-restored-and-redeployed')
    end=remote('''import sqlite3,json,subprocess
c=json.load(open('/opt/rufus/config/config.json'));db=sqlite3.connect(c['database'])
subprocess.run(['systemctl','is-active','--quiet','rufus','rufus-web'],check=True)
print(json.dumps({'executions':db.execute('SELECT count(*) FROM executions').fetchone()[0],'processing':db.execute("SELECT count(*) FROM messages WHERE status='processing'").fetchone()[0]}))''')
    assert end['executions']==baseline['executions'],'Unexpected infrastructure execution count change'
    assert end['processing']==0
    emit('PASS',zero_infrastructure_jobs=True,log=str(log),backup=baseline['backup'],limitations=['Actual VS Code visual acceptance remains separate','No real sensitive proposal created'])

if __name__=='__main__':
    try:main()
    except Exception as error:
        emit('FAIL',error=str(error));raise SystemExit(1)
