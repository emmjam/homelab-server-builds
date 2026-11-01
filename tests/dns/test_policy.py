"""Exercise real DNS policy decisions using isolated manager commands and files."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
POLICY=ROOT/'Ansible/roles/debian_dns/files/configure-debian-dns.sh'
class PolicyTests(unittest.TestCase):
 def run_policy(self,manager='netplan',twice=False):
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp);bin=base/'bin';bin.mkdir();etc=base/'etc';(etc/'dhcp').mkdir(parents=True)
   (etc/'dhcp/dhclient.conf').write_text('send host-name = gethostname();\n')
   (etc/'resolv.conf').write_text('search lan\nnameserver 192.168.0.2\n')
   commands={'ip':'echo "default via 192.168.0.1 dev eth0"','netplan':':','networkctl':'echo "Network File: /run/systemd/network/10-netplan-eth0.network"' if manager=='netplan' else 'echo unmanaged','resolvectl':':','ifquery':'exit 0' if manager=='ifupdown' else 'exit 1','pgrep':'echo "42 dhclient eth0"' if manager=='ifupdown' else 'exit 1'}
   for name,body in commands.items():
    p=bin/name;p.write_text('#!/bin/sh\nprintf "%s\\n" "'+name+' $*" >> "$CALLS"\n'+body+'\n');p.chmod(0o755)
   script=base/'policy';script.write_text(POLICY.read_text().replace('[[ $EUID == 0 ]]','[[ 1 == 1 ]]').replace('/etc/',str(etc)+'/').replace('export PATH=/usr/sbin:/usr/bin:/sbin:/bin','export PATH='+str(bin)+':/usr/sbin:/usr/bin:/sbin:/bin'))
   env=dict(os.environ,PATH=str(bin)+':'+os.environ['PATH'],CALLS=str(base/'calls'))
   r=subprocess.run(['bash',str(script)],env=env,capture_output=True,text=True)
   first=r.stdout
   if twice:r=subprocess.run(['bash',str(script)],env=env,capture_output=True,text=True)
   contents={str(p.relative_to(etc)):p.read_text() for p in etc.rglob('*') if p.is_file()}
   return r,first,contents,(base/'calls').read_text()
 def test_netplan_is_persistent_and_resolver_only(self):
  r,first,c,calls=self.run_policy(twice=True);self.assertEqual(r.returncode,0,r.stderr)
  self.assertIn('CHANGED=1',first);self.assertIn('CHANGED=0',r.stdout)
  e=yaml.safe_load(c['netplan/90-homelab-dns.yaml'])['network']['ethernets']['eth0']
  self.assertEqual(e['nameservers'],{'addresses':['192.168.0.2'],'search':['lan']})
  self.assertTrue(e['dhcp4-overrides']['send-hostname']);self.assertFalse(e['dhcp4-overrides']['use-hostname'])
  self.assertIn('netplan generate',calls);self.assertNotIn('netplan apply',calls);self.assertNotIn('networkctl renew',calls)
  self.assertEqual(c['resolv.conf'],'search lan\nnameserver 192.168.0.2\n')
 def test_ifupdown_reuses_its_client_and_keeps_generated_resolver(self):
  r,first,c,calls=self.run_policy('ifupdown',True);self.assertEqual(r.returncode,0,r.stderr)
  self.assertIn('CHANGED=0',r.stdout);self.assertEqual(c['dhcp/dhclient.conf'].count('# BEGIN HOMELAB DNS'),1)
  self.assertIn('supersede domain-search "lan";',c['dhcp/dhclient.conf'])
  self.assertNotIn('ifquery --state',calls);self.assertNotIn('netplan generate',calls);self.assertNotIn('dhclient -',calls)
  self.assertEqual(c['resolv.conf'],'search lan\nnameserver 192.168.0.2\n')
 def test_unknown_manager_fails_before_writing_network_settings(self):
  r,_,c,_=self.run_policy('unknown');self.assertNotEqual(r.returncode,0)
  self.assertNotIn('netplan/90-homelab-dns.yaml',c);self.assertNotIn('# BEGIN HOMELAB DNS',c['dhcp/dhclient.conf'])
 def test_lxc_job_search_domain_default(self):
  p=next((ROOT/'Rundeck/jobs').glob('Proxmox - Create LXC Container-*.yaml'))
  option=next(x for x in yaml.safe_load(p.read_text())[0]['options'] if x['name']=='search_domain')
  self.assertEqual(option['value'],'lan')

class RegistrationTests(unittest.TestCase):
 def test_waits_for_dns_publication_without_starting_a_dhcp_client(self):
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp);b=base/'bin';b.mkdir()
   fake='''#!/usr/bin/env python3
import os,sys,pathlib,json
n=pathlib.Path(sys.argv[0]).name
p=pathlib.Path(os.environ['STATE']);d=json.loads(p.read_text());d['calls'].append([n]+sys.argv[1:])
if n=='ip': print('default via 10.0.0.1 dev eth0' if 'route' in sys.argv else '2: eth0 inet 10.0.0.20/24 scope global eth0')
elif n=='hostname':print('dns-test')
elif n=='dig':
 d['queries']+=1
 if d['queries']>2:print('10.0.0.20')
p.write_text(json.dumps(d))
'''
   for name in ['ip','hostname','dig','sleep','cloud-init','timeout']:
    p=b/name;p.write_text(fake);p.chmod(0o755)
   state=base/'state';state.write_text(json.dumps({'calls':[],'queries':0}))
   original=(ROOT/'Ansible/roles/debian_dns/files/homelab-hostname-registration').read_text()
   script=base/'checker';script.write_text(original.replace('export PATH=/usr/sbin:/usr/bin:/sbin:/bin','export PATH='+str(b)+':/usr/bin:/bin').replace('/var/log/homelab-hostname-registration.log',str(base/'log')))
   r=subprocess.run(['bash',str(script)],env=dict(os.environ,STATE=str(state)),capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   d=json.loads(state.read_text());self.assertGreater(d['queries'],2)
   self.assertIn('SUCCESS',r.stdout);self.assertFalse(any(c[0] in ['dhclient','networkctl'] for c in d['calls']))
