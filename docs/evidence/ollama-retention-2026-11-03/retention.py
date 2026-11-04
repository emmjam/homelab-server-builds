import json,os,subprocess,shlex,pathlib,hashlib,time
ROOT=pathlib.Path(__file__).resolve().parent
log=open(ROOT/'deployment.log','a',buffering=1)
def emit(check,**data):print(json.dumps(dict(check=check,**data)),flush=True)
env={**os.environ,'ANSIBLE_CONFIG':str(ROOT/'Ansible/ansible.cfg'),'ANSIBLE_ROLES_PATH':str(ROOT/'Ansible/roles')}
base=['sudo','-u','rundeck','ssh','-i','/var/lib/rundeck/.ssh/target_ed25519','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes']
def remote(host,code,as_rufus=False):
 alias='rufus' if host=='rufus.lan' else 'ai-agent';known='managed_debian_known_hosts' if alias=='rufus' else 'known_hosts'
 command=['sudo','-n']+(['runuser','-u','rufus','--'] if as_rufus else [])+['python3','-c',code]
 return json.loads(subprocess.check_output(base+['-o','HostKeyAlias='+alias,'-o','UserKnownHostsFile=/var/lib/rundeck/.ssh/'+known,'rundeck@'+host,shlex.join(command)],text=True,timeout=420))
def ansible(*args):
 subprocess.run(['ansible-playbook','-i','Ansible/inventory/ai-inference.ini','Ansible/playbooks/ai-inference.yml','--limit','ai_inference','--tags','ollama_service_configuration',*args],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
manifest=json.loads((ROOT/'SOURCE.json').read_text())
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in manifest.items())
if not (ROOT/'facts/ai-agent.lan').exists():
 ansible('--syntax-check');emit('syntax-PASS')
else:emit('syntax-already-PASS')
# Render the exact unit using existing Ansible facts/defaults, then validate it before deploy.
subprocess.run(['ansible','-i','Ansible/inventory/ai-inference.ini','ai_inference','-m','ansible.builtin.setup','--tree',str(ROOT/'facts')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template
loader=DataLoader();defaults=loader.load_from_file(str(ROOT/'Ansible/roles/ollama_inference/defaults/main.yml'))
facts=json.loads((ROOT/'facts/ai-agent.lan').read_text())['ansible_facts']
# Ansible 2.x flattened setup keys: supply the exact fact referenced by the service template.
variables={**defaults,'ansible_facts':{'default_ipv4':facts['ansible_default_ipv4']}}
template=(ROOT/'Ansible/roles/ollama_inference/templates/ollama.service.j2').read_text()
rendered=Templar(loader=loader,variables=variables).template(trust_as_template(template),preserve_trailing_newlines=True)
before=remote('ai-agent.lan',"import json,pathlib;print(json.dumps(pathlib.Path('/etc/systemd/system/ollama.service').read_text()))")
assert before.replace('OLLAMA_KEEP_ALIVE=0','OLLAMA_KEEP_ALIVE=30m')==rendered,'Predicted unit changes more than retention; stop'
validation=remote('ai-agent.lan',"import json,pathlib,tempfile,subprocess;d=pathlib.Path(tempfile.mkdtemp(prefix='ollama-unit-check-'));p=d/'ollama-retention.service';p.write_text("+repr(rendered)+");r=subprocess.run(['systemd-analyze','verify',str(p)],capture_output=True,text=True);assert r.returncode==0,r.stderr;p.unlink();d.rmdir();print(json.dumps({'unit_syntax':'PASS'}))")
emit('rendered-config-PASS',**validation)
ansible('--check','--diff');emit('check-mode-PASS')
state=remote('ai-agent.lan',r'''
import pathlib,json,subprocess,urllib.request
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with op.open('http://ai-agent.lan:11434/api/ps',timeout=10) as r:assert not json.load(r)['models'],'Model currently loaded: defer restart'
keys=['MainPID','MemoryMax','CPUQuotaPerSecUSec','User','Group','ExecStart','DropInPaths','EnvironmentFiles']
v={k:subprocess.check_output(['systemctl','show','ollama','-p',k,'--value'],text=True).strip() for k in keys}
v['unit']=pathlib.Path('/etc/systemd/system/ollama.service').read_text()
v['model_hash']=__import__('hashlib').sha256(pathlib.Path('/usr/share/ollama/.ollama/models/manifests/registry.ollama.ai/library/qwen3/4b').read_bytes()).hexdigest()
print(json.dumps(v))
''')
rufus=remote('rufus.lan',"import json,sqlite3;from pathlib import Path;c=json.loads(Path('/opt/rufus/config/config.json').read_text());d=sqlite3.connect(c['database']);assert d.execute(\"SELECT count(*) FROM messages WHERE status='processing'\").fetchone()[0]==0,'Rufus busy';print(json.dumps({'inference_sha256':__import__('hashlib').sha256(Path('/opt/rufus/app/inference.py').read_bytes()).hexdigest()}))")
(ROOT/'before.json').write_text(json.dumps(state,indent=2))
ansible('--diff');emit('deployment-PASS')
after=remote('ai-agent.lan',r'''
import pathlib,json,subprocess,hashlib,shlex
keys=['MainPID','MemoryMax','CPUQuotaPerSecUSec','User','Group','ExecStart','DropInPaths','EnvironmentFiles']
v={k:subprocess.check_output(['systemctl','show','ollama','-p',k,'--value'],text=True).strip() for k in keys}
subprocess.run(['systemctl','is-active','--quiet','ollama'],check=True)
v['unit']=pathlib.Path('/etc/systemd/system/ollama.service').read_text()
v['model_hash']=hashlib.sha256(pathlib.Path('/usr/share/ollama/.ollama/models/manifests/registry.ollama.ai/library/qwen3/4b').read_bytes()).hexdigest()
e=pathlib.Path('/proc/'+v['MainPID']+'/environ').read_bytes().split(b'\0')
v['active_keep_alive']=next(x.decode().split('=',1)[1] for x in e if x.startswith(b'OLLAMA_KEEP_ALIVE='))
assert v['active_keep_alive']=='30m'
print(json.dumps(v))
''')
assert state['MainPID']!=after['MainPID'],'Expected one restart for changed environment'
assert state['unit'].replace('OLLAMA_KEEP_ALIVE=0','OLLAMA_KEEP_ALIVE=30m')==after['unit']
assert all(state[k]==after[k] for k in state if k not in ['MainPID','unit','ExecStart'])
(ROOT/'after.json').write_text(json.dumps(after,indent=2));emit('service-and-unchanged-resources-PASS',active_keep_alive=after['active_keep_alive'],pid=after['MainPID'])
# Final combined acceptance runs from the real unprivileged Rufus account.
result=remote('rufus.lan',r'''
import json,urllib.request,datetime,time,pathlib,hashlib
base='http://ai-agent.lan:11434';op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def call(path,body=None):
 req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
 with op.open(req,timeout=360) as r:return json.load(r)
tags=call('/api/tags');assert any(m['name']=='qwen3:4b' for m in tags['models'])
# Same existing model; do not send keep_alive, and do not change configured inference options.
body={'model':'qwen3:4b','messages':[{'role':'user','content':'Reply with just OK. /no_think'}],
      'stream':False,'think':False}
reply=call('/api/chat',body)
assert reply.get('done') is True and reply.get('done_reason')!='length' and reply.get('message',{}).get('content','').strip(),'Inference failed or incomplete'
finished=datetime.datetime.now(datetime.timezone.utc)
ps=call('/api/ps');m=next(m for m in ps['models'] if m['name']=='qwen3:4b')
expires=datetime.datetime.fromisoformat(m['expires_at'].replace('Z','+00:00'));seconds=(expires-finished).total_seconds()
assert 1740<=seconds<=1860,('Unexpected retention expiry',seconds)
time.sleep(5)
later=call('/api/ps');assert any(x['name']=='qwen3:4b' for x in later['models'])
print(json.dumps({'api_reachable_as':'rufus','model':'qwen3:4b','inference_done':True,'reply_characters':len(reply['message']['content']),
 'load_duration_ns':reply.get('load_duration'),'prompt_eval_count':reply.get('prompt_eval_count'),
 'expires_at':m['expires_at'],'retention_seconds_after_request':seconds,'still_loaded_after_seconds':5,
 'natural_30_minute_unload':'unverified; no 30-minute wait',
 'inference_sha256':hashlib.sha256(pathlib.Path('/opt/rufus/app/inference.py').read_bytes()).hexdigest()}))
''',as_rufus=True)
assert result['inference_sha256']==rufus['inference_sha256']
(ROOT/'acceptance.json').write_text(json.dumps(result,indent=2));emit('live-retention-PASS',**result)
# Check-mode verifies convergence without another restart or inference request.
ansible('--check');emit('convergence-check-PASS')
emit('PASS',evidence=str(ROOT),limitation='Rufus keep_alive=0 still overrides server default; application unchanged')
