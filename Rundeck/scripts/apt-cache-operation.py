#!/usr/bin/env python3
"""Fixed APT-cache operations. Rundeck identity owns SSH; Rufus never does."""
import json
import subprocess
import sys

if len(sys.argv)!=3 or sys.argv[1] not in ('apt-cache','fixture') or sys.argv[2] not in ('diagnose','restart','verify'):
    raise SystemExit('Unsupported fixed operation')
target,action=sys.argv[1:]
service='apt-cacher-ng' if target=='apt-cache' else 'apt-cache-ai2-fixture'
port=3142 if target=='apt-cache' else 13142
cache='/var/cache/apt-cacher-ng' if target=='apt-cache' else '/var/cache/apt-cacher-ng-ai2-fixture'
# Availability is established by this trusted SSH connection before service diagnostics.
# The APT-cache VM is always-on; no WOL/SSH/network reconfiguration is attempted.
code='''import json,shutil,subprocess,urllib.request,urllib.error
service=%r
port=%r
cache=%r
target=%r
action=%r
if action=='restart':
    subprocess.run(['sudo','-n','/usr/bin/systemctl','restart',service],check=True,timeout=30)
    print(json.dumps({'kind':'repair-submitted','target':target}))
else:
    active=subprocess.run(['systemctl','is-active',service],capture_output=True,timeout=5).returncode==0
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:'+str(port)+'/acng-report.html',timeout=5) as r:
            http_ok=r.status==200
    except (OSError,urllib.error.URLError): http_ok=False
    print(json.dumps({'kind':'apt-cache-check','target':target,'available':True,
        'service_active':active,'http_ok':http_ok,'disk_free_bytes':shutil.disk_usage(cache).free}))
''' % (service,port,cache,target,action)
ssh=['ssh','-i','/var/lib/rundeck/.ssh/target_ed25519','-o','BatchMode=yes','-o','ConnectTimeout=8',
     '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=/var/lib/rundeck/.ssh/managed_debian_known_hosts',
     '-o','HostKeyAlias=apt-cache','rundeck@apt-cache.lan','python3','-']
try:
    result=subprocess.run(ssh,input=code,text=True,capture_output=True,timeout=45)
except subprocess.TimeoutExpired:
    # Mutations may have completed: never retry an uncertain submission.
    raise SystemExit('Operation timed out; check execution before any new repair') from None
if result.returncode:
    if action!='restart' and result.returncode==255:
        print(json.dumps({'kind':'apt-cache-check','target':target,'available':False,
                         'service_active':False,'http_ok':False,'disk_free_bytes':0}))
        raise SystemExit(0)
    raise SystemExit('Fixed operation failed; inspect administrative logs')
# Only emit the controlled structured response, never SSH exception bodies.
for line in result.stdout.splitlines():
    try: data=json.loads(line)
    except ValueError: continue
    print(json.dumps(data))
