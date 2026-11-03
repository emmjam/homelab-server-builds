#!/usr/bin/env python3
"""Controller-only final Task 3 acceptance. Never wakes or contacts Macs."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
JOB = '7d9a3328-c8df-4e31-bbf6-49a6d9ce5a11'


def main():
    with tempfile.NamedTemporaryFile(mode='w', prefix='worker-power-final-',
                                     suffix='.log', delete=False) as output:
        log = Path(output.name)
        print('LOG', log, flush=True)
        def command(args):
            subprocess.run(args, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
        if '--live-only' not in sys.argv:
            for suite in ('rundeck', 'rufus'):
                command([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests/'+suite, '-v'])
                print('PASS tests-'+suite, flush=True)
            command(['bash', '-n', 'Rundeck/scripts/power-ai-host.sh'])
            command(['ansible-playbook', '-i', 'Ansible/inventory/ai-inference.ini', '-i',
                     'Ansible/inventory/ai2.ini', '-i', 'Ansible/inventory/compute.yml',
                     'Ansible/playbooks/worker-power.yml'])
            print('PASS controller deployment', flush=True)
        # Read the actual active restricted token in memory; never emit secrets.
        raw = subprocess.check_output(['sudo','-u','rundeck','ssh','-i',
            '/var/lib/rundeck/.ssh/target_ed25519','-o','BatchMode=yes','-o',
            'HostKeyAlias=rufus','-o','UserKnownHostsFile=/var/lib/rundeck/.ssh/managed_debian_known_hosts',
            '-o','StrictHostKeyChecking=yes','rundeck@rufus.lan','sudo','-n','cat',
            '/opt/rufus/config/secrets.txt'], text=True)
        import shlex
        entries = dict(line.partition('=')[::2] for line in raw.splitlines() if '=' in line)
        token = shlex.split(entries['RUFUS_RUNDECK_TOKEN'])[0]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def api(path, body=None):
            request = urllib.request.Request('http://127.0.0.1:4440/api/50/'+path,
                data=None if body is None else json.dumps(body).encode(),
                headers={'X-Rundeck-Auth-Token':token, 'Accept':'application/json','Content-Type':'application/json'})
            with opener.open(request, timeout=15) as response:
                return json.load(response)
        # Existing filesystem ACLs are cached by Rundeck; wait without restart.
        for attempt in range(76):
            try:
                assert api('job/'+JOB+'/info')['id'] == JOB
                break
            except urllib.error.HTTPError as error:
                if error.code != 403 or attempt == 75:
                    raise
                if attempt % 15 == 0:
                    print('WAIT existing Rundeck ACL cache reload', flush=True)
                time.sleep(2)
        if '--power-only' not in sys.argv:
            try:
                api('job/769ed228-0054-4a3a-bee5-c110af96ff48/info')
            except urllib.error.HTTPError as error:
                assert error.code in (403,404), error.code
            else:
                raise AssertionError('Restricted token can read unrelated VM job')
            try:
                api('job/'+JOB+'/run', {'options':{'vmname':'tnas','action':'wake'}})
            except urllib.error.HTTPError as error:
                assert error.code == 400, error.code
            else:
                raise AssertionError('Invalid worker accepted by Rundeck')
            print('PASS restricted job read and unrelated-job/invalid-worker denial', flush=True)
        def execute(host, action, success):
            execution = api('job/'+JOB+'/run', {'options':{'vmname':host,'action':action}})['id']
            deadline = time.monotonic()+200
            while time.monotonic()<deadline:
                state=api('execution/'+str(execution))['status']
                if state not in ('running','queued','scheduled'):
                    break
                time.sleep(2)
            else:
                raise AssertionError('Execution timeout: '+str(execution))
            data=api('execution/'+str(execution)+'/output?format=json')
            messages='\n'.join(e.get('log','') for e in data.get('entries',[]))
            output.write(f'EXECUTION {execution} {host} {action} {state}\n'+messages+'\n')
            output.flush()
            assert (state=='succeeded') == success, (execution,state)
            print(f'PASS {host} {action}: {state}, execution {execution}',flush=True)
            return messages
        workers = ('ai-worker',) if '--dell-only' in sys.argv else ('ai-agent','ai-worker')
        failures = []
        for host in workers:
            started = int(time.time())
            try:
                messages=execute(host,'wake',True)
                assert 'WAKE VERIFIED' in messages or 'already reachable' in messages
            except (AssertionError, subprocess.CalledProcessError) as error:
                failures.append((host, 'wake availability unresolved', str(error)))
                print('FAIL '+host+' wake verification; suspend skipped', flush=True)
                continue
            try:
                messages=execute(host,'sleep',True)
                assert 'Actual sleep state is not independently verified' in messages
                messages=execute(host,'wake',True)
                assert 'WAKE VERIFIED' in messages or 'already reachable' in messages
                config = json.loads(Path('/opt/rufus-power/config.json').read_text())
                node = config['workers'][host]
                for name in (host,host+'.lan'):
                    address = subprocess.check_output(['getent','ahostsv4',name],text=True).split()[0]
                    assert address, 'DNS missing after resume: '+name
                    output.write(name+' resolves to '+address+'\n')
                ssh = ['sudo','-u','rundeck','ssh','-i',config['ssh_key'],
                    '-o','BatchMode=yes','-o','ConnectTimeout=5',
                    '-o','StrictHostKeyChecking=yes','-o','HostKeyAlias='+node['host_key_alias'],
                    '-o','UserKnownHostsFile='+config['known_hosts'],node['user']+'@'+node['host']]
                kernel = subprocess.check_output(ssh+['sudo','-n','journalctl','-b','-k',
                    '--since','@'+str(started),'--no-pager','-o','cat'],text=True)
                dhcp = subprocess.check_output(ssh+['sudo','-n','journalctl','-b','_COMM=dhclient',
                    '--since','@'+str(started),'--no-pager','-o','cat'],text=True)
                output.write('KERNEL '+host+'\n'+kernel+'\nDHCP '+host+'\n'+dhcp+'\n')
                assert 'PM: suspend entry (deep)' in kernel, 'No independent deep suspend entry'
                assert 'PM: suspend exit' in kernel, 'No independent resume evidence'
                assert 'DHCPACK' in dhcp, 'No fresh DHCP ACK after resume'
                print('PASS '+host+' independent deep suspend/resume, fresh DHCP ACK and short/FQDN DNS', flush=True)
            except (AssertionError, subprocess.CalledProcessError) as error:
                failures.append((host, 'suspend unverified', str(error)))
                print('FAIL '+host+' suspend verification', flush=True)
        if failures:
            print('FAIL power acceptance: '+json.dumps(failures), flush=True)
            return 1
        print('PASS '+','.join(workers)+' wake availability and suspend request/disconnect evidence; Macs not contacted',flush=True)
    print('PASS Task 3 final acceptance; log '+str(log),flush=True)


if __name__ == '__main__':
    sys.exit(main())
