"""Controller-only fixed read probes. No power commands or model-supplied input."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time

REMOTE_COMMAND='python3 -'
PUBLISH_COMMAND='python3 /usr/local/lib/rufus-discovery-publish.py'

def valid_host(value):return isinstance(value,str) and bool(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}',value))
def validate(config):
    seen=set()
    for n in config['nodes']:
        if (not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',n['id']) or n['id'] in seen
                or not all(valid_host(n['ssh'][k]) for k in ('host','user','host_key_alias'))):raise ValueError('Invalid inventory identity')
        seen.add(n['id'])
    if len(seen)>100:raise ValueError('Inventory too large')
    if not 60<=config['interval_seconds']<=86400 or config['stale_seconds']<=config['interval_seconds']:raise ValueError('Invalid discovery intervals')
def ssh(config,identity,command):
    return ['ssh','-T','-i',config['ssh_key'],'-o','BatchMode=yes','-o','IdentitiesOnly=yes',
            '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+config['known_hosts'],
            '-o','HostKeyAlias='+identity['host_key_alias'],'-o','ConnectTimeout=3',
            '-o','ConnectionAttempts=1','-o','ServerAliveInterval=3','-o','ServerAliveCountMax=1',
            identity['user']+'@'+identity['host'],command]
def offline(evidence,now,ttl):
    # Only explicit, independently supplied recent power evidence can mean sleep.
    if (isinstance(evidence,dict) and evidence.get('state')=='sleeping' and evidence.get('source')
            and isinstance(evidence.get('observed_at'),(int,float))
            and 0<=now-evidence['observed_at']<=ttl):return 'sleeping'
    return 'unreachable'
def availability(facts,node,config):
    root=next(d for d in facts['hardware']['storage'] if d['mount']=='/')
    metrics=facts['metrics'];total=facts['hardware']['ram_bytes'];free=metrics['memory_available_bytes']
    healthy=facts['health']=='running' and not root['read_only'] and root['available_bytes']>=config['min_disk_bytes']
    busy=(metrics['cpu_busy_percent']>=config['busy_cpu_percent'] or free/max(1,total)*100<config['busy_memory_percent'])
    state='online_unavailable' if not healthy else ('online_busy' if busy else 'online_available')
    workloads={}
    for workload in node['supported_workloads']:
        status='available' if healthy and not busy else 'busy' if healthy else 'unavailable'
        reason=None if status=='available' else 'Node busy' if healthy else 'OS health or workspace capacity check failed'
        if workload=='inference' and not (facts['runtimes']['ollama']['reachable'] and facts['runtimes']['ollama']['models']):
            status,reason='unavailable','Ollama or installed models unavailable'
        if workload=='virtualisation' and not facts['runtimes'].get('proxmox',False):
            # The inventory declares eligibility, not permission to allocate guests.
            status,reason='unavailable','Virtualisation workload readiness not verified by this probe'
        workloads[workload]={'state':status,'reason':reason}
    return state,workloads

def check(node,previous,config,probe,clock=time.time,run=subprocess.run,connect=socket.create_connection):
    now=clock();record=dict(node);record['last_success_at']=previous.get('last_success_at')
    record['last_verified_capabilities']=previous.get('last_verified_capabilities')
    observation={'checked_at':now,'awake':None,'ssh_available':False,'state':'unreachable','metrics':None,'health':None,
                 'workloads':{w:{'state':'unavailable','reason':'Current availability not verified'} for w in node['supported_workloads']}}
    record['observation']=observation
    try:
        with connect((node['ssh']['host'],22),timeout=2):pass
    except OSError:
        ping=shutil.which('ping')
        try:awake=bool(ping and run([ping,'-n','-c','1','-W','1',node['ssh']['host']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2).returncode==0)
        except subprocess.TimeoutExpired:awake=False
        observation.update(state='online_unavailable' if awake else offline(node.get('power_evidence'),now,config['stale_seconds']),awake=True if awake else None)
        if observation['state']=='sleeping':observation['awake']=False
        observation['reason']='SSH unavailable; ICMP responded' if awake else 'Recent independent sleep evidence' if observation['state']=='sleeping' else 'No current reachability evidence; sleep is not assumed'
        return record
    observation['awake']=True;observation['state']='online_unavailable'
    try:
        program='OLLAMA_URL = '+repr('http://'+node['ssh']['host']+':11434')+'\n'+probe
        result=run(ssh(config,node['ssh'],REMOTE_COMMAND),input=program,text=True,capture_output=True,timeout=config['ssh_timeout_seconds'])
        observation['ssh_available']=result.returncode!=255
        if result.returncode:raise ValueError('SSH access or probe failed')
        if len(result.stdout)>262144:raise ValueError('Oversize probe output')
        facts=json.loads(result.stdout)
        if facts['hostname']!=node['id']:raise ValueError('Node identity mismatch')
        state,workloads=availability(facts,node,config)
        observation.update(state=state,health=facts['health'],metrics=facts['metrics'],workloads=workloads)
        record['last_success_at']=now
        record['last_verified_capabilities']={'verified_at':now,'source':'fixed SSH read-only probe',
            **{k:facts[k] for k in ('hardware','os','power','runtimes')}}
    except (OSError,ValueError,KeyError,TypeError,StopIteration,subprocess.TimeoutExpired) as error:
        observation['reason']=str(error) if isinstance(error,ValueError) else 'SSH probe unavailable or invalid'
    return record

def atomic(path,data):
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.nodes-')
    try:
        with os.fdopen(fd,'w') as f:json.dump(data,f,separators=(',',':'));f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);args=parser.parse_args()
    config=json.loads(Path(args.config).read_text());validate(config)
    state=Path(config['state_file'])
    with open(str(state)+'.lock','w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        try:previous={n['id']:n for n in json.loads(state.read_text())['nodes']}
        except (OSError,ValueError,KeyError,TypeError):previous={}
        probe=Path(config['probe_file']).read_text()
        with ThreadPoolExecutor(max_workers=3) as pool:
            records=list(pool.map(lambda n:check(n,previous.get(n['id'],{}),config,probe),config['nodes']))
        snapshot={'schema_version':1,'collected_at':time.time(),'stale_seconds':config['stale_seconds'],'nodes':records}
        atomic(state,snapshot)
        result=subprocess.run(ssh(config,config['publisher'],PUBLISH_COMMAND),input=json.dumps(snapshot),text=True,capture_output=True,timeout=20)
        if result.returncode:raise SystemExit('Snapshot publication failed; cached controller state retained')
        print(json.dumps({'status':'published','nodes':{n['id']:n['observation']['state'] for n in records}}))
if __name__=='__main__':main()
