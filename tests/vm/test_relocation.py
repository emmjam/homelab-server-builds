"""Service-ID relocation guards and rollback with fake Proxmox commands."""
import json, os, subprocess, tempfile, unittest
from pathlib import Path
SCRIPT=Path(__file__).resolve().parents[2]/'Rundeck/scripts/provision-vm.sh'
FAKE='''#!/usr/bin/env python3
import json,os,pathlib,sys
p=pathlib.Path(os.environ['STATE']);s=json.loads(p.read_text());a=sys.argv[1:];s['calls'].append(a)
def save():p.write_text(json.dumps(s))
if pathlib.Path(sys.argv[0]).name=='pvesh':print(json.dumps([{'vmid':int(k)} for k in s['vms']]))
elif a[0]=='config':print('name: '+s['vms'][a[1]]+'\\nnet0: virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr0')
elif a[0]=='shutdown':s['status'][a[1]]='stopped'
elif a[0]=='status':print('status: '+s['status'].get(a[1],'running'))
elif a[0]=='clone':s['vms'][a[2]]=s['vms'][a[1]]
elif a[0]=='stop':s['status'][a[1]]='stopped'
elif a[0]=='start':s['status'][a[1]]='running'
elif a[:2]==['guest','exec']:print(json.dumps({'exitcode':1 if os.environ.get('FAIL') else 0}))
elif a[0]=='destroy':del s['vms'][a[1]]
save()
'''
class RelocationTests(unittest.TestCase):
 def run_move(self,occupied=False,failure=False,pair=('9001','112')):
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp);state=d/'state';state.write_text(json.dumps({'vms':{'9001':'Apt-Cache',**({'112':'other'} if occupied else {})},'status':{},'calls':[]}))
   for n in ['qm','pvesh']:(d/n).write_text(FAKE);(d/n).chmod(0o755)
   for n in ['flock','sleep']:(d/n).write_text('#!/bin/sh\nexit 0\n');(d/n).chmod(0o755)
   script=d/'script';script.write_text(SCRIPT.read_text().replace('$EUID == 0','1 == 1').replace('/run/lock/homelab-service-migration.lock',str(d/'lock')))
   r=subprocess.run(['bash',str(script),'--relocate-service',*pair],env=dict(os.environ,PATH=str(d)+':'+os.environ['PATH'],STATE=str(state),FAIL='1' if failure else ''),capture_output=True,text=True)
   return r,json.loads(state.read_text())
 def test_success_preserves_network_and_deletes_source_last(self):
  r,s=self.run_move();self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(s['vms'],{'112':'Apt-Cache'})
  self.assertIn(['set','112','--net0','virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr0'],s['calls'])
  self.assertEqual(s['calls'][-1],['destroy','9001','--purge','1'])
 def test_occupied_destination_is_untouched(self):
  r,s=self.run_move(occupied=True);self.assertNotEqual(r.returncode,0);self.assertFalse(any(c[0]=='shutdown' for c in s['calls']))
 def test_failed_service_rolls_back_without_deletion(self):
  r,s=self.run_move(failure=True);self.assertNotEqual(r.returncode,0);self.assertEqual(s['status']['9001'],'running');self.assertEqual(s['status']['112'],'stopped');self.assertFalse(any(c[0]=='destroy' for c in s['calls']))
 def test_unapproved_pair_has_no_effect(self):
  r,s=self.run_move(pair=('9000','112'));self.assertNotEqual(r.returncode,0);self.assertEqual(s['calls'],[])
