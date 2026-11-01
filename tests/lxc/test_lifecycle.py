"""Validate destructive guards and clone cleanup with isolated fake Proxmox state."""
import json
import os
import subprocess
from test_template import ProxmoxFixture

BASELINE = 'tags: homelab-debian-lxc\ntemplate: 1\nrootfs: local-zfs:base-9100-disk-0,size=4G\n'

class LifecycleTests(ProxmoxFixture):
    def run_action(self, script, args, cts=None, failure='', statuses=None):
        self.state.write_text(json.dumps({'cts': cts or {}, 'calls': [], 'status': statuses or {}}))
        result = subprocess.run(['bash', str(self.base / 'scripts' / script), *args],
            env=dict(os.environ, STATE=str(self.state), FAIL=failure), capture_output=True, text=True)
        return result, json.loads(self.state.read_text())

    def create_args(self):
        return ['--id','220','--hostname','lxc-test','--cores','2','--memory','1',
                '--disk','6','--storage','local-zfs','--bridge','vmbr0',
                '--ip','dhcp','--dns','192.168.0.2','--template-id','9100']

    def test_provision_resources(self):
        result, state = self.run_action('create-container.sh', self.create_args(), {'9100':BASELINE})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('cores: 2',state['cts']['220'])
        self.assertIn('memory: 1024',state['cts']['220'])
        self.assertIn('size=6G',state['cts']['220'])
        self.assertEqual(state['cts']['9100'],BASELINE)
        net = next(c for c in state['calls'] if c[:2]==['pct','set'])
        self.assertRegex(net[net.index('--net0')+1],r'hwaddr=02:([0-9a-f]{2}:){4}[0-9a-f]{2},ip=dhcp')

    def test_provision_failure_cleans_own_target(self):
        result, state = self.run_action('create-container.sh', self.create_args(), {'9100':BASELINE,'110':'rufus'},'start')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(state['cts'],{'9100':BASELINE,'110':'rufus'})

    def test_existing_id_is_untouched(self):
        result,state=self.run_action('create-container.sh',self.create_args(),{'9100':BASELINE,'220':'existing'})
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(state['cts']['220'],'existing')
        self.assertFalse(any(c[:2]==['pct','destroy'] for c in state['calls']))

    def test_invalid_parameters_never_mutate(self):
        mutations={'create','clone','set','resize','start','stop','shutdown','destroy'}
        for flag,value in [('--id',''),('--id','0'),('--id','110'),('--id','00110'),('--id','220;id'),
                           ('--cores','0'),('--memory','-1'),('--memory','1.5'),('--disk','3'),
                           ('--hostname','bad name'),('--dns','999.1.1.1'),('--ip','192.168.0.999/24'),
                           ('--storage','local;id'),('--bridge','vmbr0,tag=2'),('--template-id','x')]:
            with self.subTest(flag=flag,value=value):
                args=self.create_args();args[args.index(flag)+1]=value
                result,state=self.run_action('create-container.sh',args,{'9100':BASELINE})
                self.assertNotEqual(result.returncode,0)
                self.assertFalse(any(c[0]=='pct' and c[1] in mutations for c in state['calls']))

    def test_static_ip_and_gateway_validation(self):
        args=self.create_args();args[args.index('--ip')+1]='192.168.0.220/24'
        result,state=self.run_action('create-container.sh',args+['--gateway','10.0.0.1'],{'9100':BASELINE})
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(state['calls'])

    def test_delete_requires_id_specific_confirmation(self):
        for args in [[],['--id',''],['--id','x'],['--id','220'],['--id','220','--confirm','yes'],['--id','220','--confirm','DELETE-221']]:
            with self.subTest(args=args):
                result,state=self.run_action('delete-container.sh',args,{'220':'test'})
                self.assertNotEqual(result.returncode,0)
                self.assertFalse(state['calls'])

    def test_templates_and_protection_are_not_deleted(self):
        for ctid,config in [('9100',BASELINE),('220','protection: 1\n'),('110','rufus')]:
            with self.subTest(ctid=ctid):
                result,state=self.run_action('delete-container.sh',['--id',ctid,'--confirm','DELETE-'+ctid],{ctid:config})
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(state['cts'],{ctid:config})
                self.assertFalse(any(c[:2]==['pct','destroy'] for c in state['calls']))

    def test_missing_container_is_not_deleted(self):
        result,state=self.run_action('delete-container.sh',['--id','220','--confirm','DELETE-220'],{'110':'rufus'})
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(any(c[:2]==['pct','destroy'] for c in state['calls']))

    def test_clean_shutdown_before_deletion(self):
        result,state=self.run_action('delete-container.sh',['--id','220','--confirm','DELETE-220'],{'220':'test'},statuses={'220':'running'})
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertNotIn('220',state['cts'])
        ops=[c[1] for c in state['calls'] if c[0]=='pct']
        self.assertLess(ops.index('shutdown'),ops.index('destroy'))
        self.assertNotIn('stop',ops)

    def test_shutdown_failure_never_destroys(self):
        result,state=self.run_action('delete-container.sh',['--id','220','--confirm','DELETE-220'],{'220':'test'},'shutdown',{'220':'running'})
        self.assertNotEqual(result.returncode,0)
        self.assertIn('220',state['cts'])
        self.assertFalse(any(c[:2]==['pct','destroy'] for c in state['calls']))
