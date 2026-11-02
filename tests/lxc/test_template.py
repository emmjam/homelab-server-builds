"""Offline Proxmox state-machine tests; no real Proxmox commands execute."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FAKE = r'''#!/usr/bin/env python3
import json,os,pathlib,sys
path=pathlib.Path(os.environ['STATE'])
s=json.loads(path.read_text())
a=sys.argv[1:]; cmd=pathlib.Path(sys.argv[0]).name
s['calls'].append([cmd]+a)
def save(): path.write_text(json.dumps(s))
def fail(): save(); sys.exit(1)
if cmd=='pvesh':
 if '/cluster/resources' in a: print(json.dumps([dict(vmid=int(k),type='lxc') for k in s['cts']]))
 elif '/cluster/nextid' in a:
  print(next(i for i in range(200,999) if str(i) not in s['cts']))
elif cmd=='pveam':
 if a[0]=='available': print('system debian-13-standard_13.6-1_amd64.tar.zst')
elif cmd=='ansible-playbook':
 if os.environ.get('FAIL')=='baseline': fail()
 print('200 : ok=20 changed=0 unreachable=0 failed=0 skipped=0')
elif cmd=='pct':
 op,ct=a[:2]
 if op=='config':
    if ct not in s['cts']: fail()
    print(s['cts'][ct])
 elif op=='create':
    if ct in s['cts']: fail()
    config='tags: '+a[a.index('--tags')+1]+'\n'
    if '--hostname' in a: config+='hostname: '+a[a.index('--hostname')+1]+'\n'
    if '--net0' in a:
     network=a[a.index('--net0')+1]
     if 'hwaddr=' not in network: network+=',hwaddr=02:00:00:00:00:01'
     config+='net0: '+network+'\n'
    if '--nameserver' in a: config+='nameserver: '+a[a.index('--nameserver')+1]+'\n'
    s['cts'][ct]=config
 elif op=='clone':
    target=a[2]
    if target in s['cts']: fail()
    if os.environ.get('FAIL')=='publish' and target=='9001': fail()
    s['cts'][target]=s['cts'][ct].replace('template: 1\n','')
 elif op=='template': s['cts'][ct]+='template: 1\n'
 elif op=='destroy': s['cts'].pop(ct,None)
 elif op=='set':
    config=s['cts'][ct]
    if '--delete' in a:
     import re
     for field in a[a.index('--delete')+1].split(','):
        config=re.sub(r'^'+field+r': .*\n','',config,flags=re.M)
    if '--net0' in a:
     import re
     config=re.sub(r'^net0: .*\n','',config,flags=re.M)
     config+='net0: '+a[a.index('--net0')+1]+'\n'
    for flag,field in [('--cores','cores'),('--memory','memory'),('--hostname','hostname'),('--tags','tags')]:
     if flag in a:
        import re
        config=re.sub(r'^'+field+r': .*\n','',config,flags=re.M)
        config+=field+': '+a[a.index(flag)+1]+'\n'
    if '--nameserver' in a:
     import re
     config=re.sub(r'^nameserver: .*\n','',config,flags=re.M)
     config+='nameserver: '+a[a.index('--nameserver')+1]+'\n'
    s['cts'][ct]=config
 elif op=='resize':
  import re
  s['cts'][ct]=re.sub(r'size=[0-9.]+G','size='+a[3],s['cts'][ct])
 elif op=='start':
  if os.environ.get('FAIL')=='start': fail()
  s.setdefault('status',{})[ct]='running'
 elif op=='shutdown':
  if os.environ.get('FAIL')=='shutdown': fail()
  s.setdefault('status',{})[ct]='stopped'
 elif op=='status':
  if ct not in s['cts']: fail()
  print('status: '+s.get('status',{}).get(ct,'stopped'))
save()
'''

class ProxmoxFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        (self.base / 'scripts').mkdir()
        for name in ['build-template.sh','common.sh','create-container.sh','delete-container.sh']:
            shutil.copy(ROOT / 'Rundeck/scripts' / name, self.base / 'scripts' / name)
        with (self.base / 'scripts/common.sh').open('a') as stream:
            stream.write('\nroot_and_lock() { :; }\nstorage() { :; }\nbridge() { :; }\nwait_ready() { :; }\n')
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        for name in ('pct', 'pvesh', 'pveam', 'ansible-playbook'):
            p = self.bin / name
            p.write_text(FAKE)
            p.chmod(0o755)
        # The production PATH is intentionally fixed; adapt only the test copy.
        common = self.base / 'scripts/common.sh'
        common.write_text(common.read_text().replace('export PATH=/usr/sbin:/usr/bin:/sbin:/bin', f'export PATH={self.bin}:/usr/sbin:/usr/bin:/sbin:/bin'))
        self.state = self.base / 'state.json'
        self.build_state = self.base / 'build.state'
        script = self.base / 'scripts/build-template.sh'
        script.write_text(script.read_text().replace('/run/homelab-lxc-build.state',str(self.build_state)))

    def run_build(self, cts=None, failure=''):
        self.state.write_text(json.dumps({'cts': cts or {}, 'calls': []}))
        env=dict(os.environ, STATE=str(self.state), FAIL=failure)
        script=str(self.base / 'scripts/build-template.sh')
        result=subprocess.run(['bash',script,'--prepare'],env=env,capture_output=True,text=True)
        if result.returncode == 0:
            import re
            candidate=re.search(r'^LXC_CANDIDATE_ID=(\d+)$',result.stdout,re.M)[1]
            phase='--abort' if failure=='baseline' else '--complete'
            result=subprocess.run(['bash',script,phase,candidate],env=env,capture_output=True,text=True)
            if failure=='baseline': result.returncode=1
        return result, json.loads(self.state.read_text())



class TemplateTests(ProxmoxFixture):
    def test_migrate_template_ids_and_preserve_conflicts(self):
        original = 'tags: homelab-debian-lxc\ntemplate: 1\n'
        for occupied in (False, True):
            with self.subTest(occupied=occupied):
                cts = {'9100': original}
                if occupied:
                    cts['9001'] = 'Apt-Cache'
                self.state.write_text(json.dumps({'cts': cts, 'calls': []}))
                result = subprocess.run(['bash', str(self.base/'scripts/build-template.sh'),
                    '--migrate-template-ids'], env=dict(os.environ, STATE=str(self.state)),
                    capture_output=True, text=True)
                state = json.loads(self.state.read_text())
                self.assertEqual(result.returncode == 0, not occupied, result.stdout + result.stderr)
                if occupied:
                    self.assertEqual(state['cts'], cts)
                else:
                    self.assertEqual(set(state['cts']), {'9001', '9998'})
                    self.assertIn('template: 1', state['cts']['9001'])
                    self.assertIn('template: 1', state['cts']['9998'])

    def test_delete_obsolete_backup_is_scoped(self):
        configs = [
            ('hostname: debian-lxc-backup-102\ntemplate: 1\ntags: homelab-debian-lxc\n', True),
            ('hostname: rufus\ntemplate: 1\ntags: homelab-debian-lxc\n', False),
            ('hostname: debian-lxc-backup-102\ntemplate: 1\ntags: homelab-debian-lxc\nprotection: 1\n', False),
            ('hostname: debian-lxc-backup-102\ntemplate: 1\n', False),
        ]
        for config, allowed in configs:
            with self.subTest(config=config):
                self.state.write_text(json.dumps({'cts': {'102': config, '111': 'rufus'}, 'calls': []}))
                result = subprocess.run(['bash', str(self.base/'scripts/build-template.sh'),
                    '--delete-obsolete-backup', '102', 'DELETE-102'],
                    env=dict(os.environ, STATE=str(self.state)), capture_output=True, text=True)
                state = json.loads(self.state.read_text())
                self.assertEqual(result.returncode == 0, allowed, result.stdout + result.stderr)
                self.assertEqual('102' not in state['cts'], allowed)
                self.assertIn('111', state['cts'])

    def test_unrelated_backup_id_is_preserved(self):
        result, state = self.run_build({'9001': 'tags: homelab-debian-lxc\ntemplate: 1\n',
                                        '9998': 'hostname: unrelated\ntemplate: 1\n'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('9001', state['cts'])
        self.assertEqual(state['cts']['9998'], 'hostname: unrelated\ntemplate: 1\n')

    def test_first_build(self):
        result, state = self.run_build({'110': 'hostname: rufus\n'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('template: 1', state['cts']['9001'])
        self.assertIn('nameserver: 192.168.0.2', state['cts']['9001'])
        self.assertIn('ip=dhcp', state['cts']['9001'])
        self.assertNotIn('hostname:', state['cts']['9001'])
        self.assertNotIn('searchdomain:', state['cts']['9001'])
        self.assertEqual(set(state['cts']), {'110', '9001'})

    def test_baseline_failure_preserves_existing(self):
        original = 'tags: homelab-debian-lxc\ntemplate: 1\n'
        result, state = self.run_build({'9001': original, '110': 'rufus'}, 'baseline')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state['cts'], {'9001': original, '110': 'rufus'})

    def test_rebuild_keeps_backup(self):
        result, state = self.run_build({'9001': 'tags: homelab-debian-lxc\ntemplate: 1\n'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(set(state['cts']), {'9998', '9001'})
        self.assertIn('template: 1', state['cts']['9998'])

    def test_failed_publication_keeps_working_backup(self):
        result, state = self.run_build({'9001': 'tags: homelab-debian-lxc\ntemplate: 1\n'}, 'publish')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(set(state['cts']), {'9998'})
        self.assertIn('template: 1', state['cts']['9998'])

    def test_refuse_unmanaged_target(self):
        result, state = self.run_build({'9001': 'template: 1\n'})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call[:2] == ['pct', 'destroy'] for call in state['calls']))

    def test_guest_transport_rejects_production_id(self):
        self.state.write_text(json.dumps({'cts':{'110':'rufus'},'calls':[]}))
        self.build_state.write_text("CANDIDATE=200\nTEMPLATE_ID=9001\nSTORAGE=local-zfs\nBUILD_TOKEN=build-test\n")
        result=subprocess.run(['bash',str(self.base/'scripts/build-template.sh'),'--ansible-exec','110','aWQ='],env=dict(os.environ,STATE=str(self.state)),capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(json.loads(self.state.read_text())['calls'])

    def test_guest_transport_rejects_wrong_ownership_tag(self):
        self.state.write_text(json.dumps({'cts':{'200':'tags: unrelated\n'},'calls':[]}))
        self.build_state.write_text("CANDIDATE=200\nTEMPLATE_ID=9001\nSTORAGE=local-zfs\nBUILD_TOKEN=build-test\n")
        result=subprocess.run(['bash',str(self.base/'scripts/build-template.sh'),'--ansible-exec','200','aWQ='],env=dict(os.environ,STATE=str(self.state)),capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(any(c[:2]==['pct','exec'] for c in json.loads(self.state.read_text())['calls']))

if __name__ == '__main__':
    unittest.main()
