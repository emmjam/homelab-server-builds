"""Exercise the existing shell entry point with isolated SSH/WOL fakes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
JOB = '7d9a3328-c8df-4e31-bbf6-49a6d9ce5a11'


class WorkerPowerTests(unittest.TestCase):
    def run_power(self, worker='ai-agent', action='wake', mode='online'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / 'key'
            key.touch()
            config = root / 'config.json'
            config.write_text(json.dumps(dict(ssh_key=str(key), known_hosts='trusted', workers={
                'ai-agent': dict(mac='10:62:e5:0d:17:a4', broadcast='255.255.255.255',
                                 host='ai-agent.lan', user='rundeck', host_key_alias='ai-agent', suspend_enabled=True),
                'server1': dict(mac='00:1d:4f:46:53:44', broadcast='192.168.0.255',
                                host='server1', user='rundeck', host_key_alias='server1', suspend_enabled=False)})))
            script = root / 'power.sh'
            script.write_text((ROOT / 'Rundeck/scripts/power-ai-host.sh').read_text().replace(
                '/opt/rufus-power/config.json', str(config)))
            log = root / 'calls'
            for name, content in {
                'sleep': '#!/bin/sh\nexit 0\n',
                'ssh': '''#!/bin/sh
printf 'SSH %s\\n' "$*" >> "$CALLS"
case "$*" in
 *'hostname -s')
  [ "$MODE" = offline ] && exit 255
  [ "$MODE" = waking ] && ! test -f "$CALLS.awake" && exit 255
  [ "$MODE" = mismatch ] && { echo other; exit 0; }
  echo ai-agent; exit 0;;
 *'sudo -n /usr/bin/systemctl --no-block suspend')
  [ "$MODE" = rejected ] && exit 1
  exit 0;;
 *' true') exit 255;;
esac
exit 0
''',
                'python3': '''#!/bin/sh
case "$2" in
 *config.json) exec /usr/bin/python3 "$@";;
 *) echo PACKET >> "$CALLS"; touch "$CALLS.awake"; exit 0;;
esac
''',
            }.items():
                p = root / name
                p.write_text(content)
                p.chmod(0o755)
            result = subprocess.run(['bash', str(script)], env=dict(os.environ,
                PATH=str(root)+':'+os.environ['PATH'], RD_OPTION_VMNAME=worker,
                RD_OPTION_ACTION=action, MODE=mode, CALLS=str(log)), capture_output=True, text=True)
            return result, log.read_text() if log.exists() else ''

    def test_already_awake_no_packet_and_strict_trust(self):
        result, calls = self.run_power()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('PACKET', calls)
        self.assertIn('StrictHostKeyChecking=yes', calls)
        self.assertIn('HostKeyAlias=ai-agent', calls)

    def test_unverified_wake_is_failure_with_honest_result(self):
        result, calls = self.run_power(mode='offline')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls.count('PACKET'), 1)
        self.assertIn('does not prove hardware wake failed', result.stderr)

    def test_wake_waits_for_matching_ssh_identity(self):
        result, calls = self.run_power(mode='waking')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('WAKE VERIFIED', result.stdout)
        self.assertEqual(calls.count('PACKET'), 1)

    def test_identity_mismatch_does_not_send_packet(self):
        result, calls = self.run_power(mode='mismatch')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('PACKET', calls)

    def test_suspend_disconnect_is_not_sleep_proof(self):
        result, calls = self.run_power(action='sleep')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('not independently verified', result.stdout)
        self.assertNotIn('PACKET', calls)

    def test_rejected_suspend_cannot_be_success(self):
        result, _ = self.run_power(action='sleep', mode='rejected')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('power state unverified', result.stderr)

    def test_mac_suspend_and_unapproved_input_do_no_io(self):
        for worker, action in [('server1','sleep'), ('tnas','wake'), ('ai-agent;true','wake'), ('ai-agent','reboot')]:
            result, calls = self.run_power(worker, action)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(calls, '')

    def test_job_acl_and_inventory(self):
        job = yaml.safe_load(next((ROOT/'Rundeck/jobs').glob('*'+JOB+'.yaml')).read_text())[0]
        self.assertEqual(job['options'][0]['values'], ['ai-agent','ai-worker','server1','server2'])
        self.assertTrue(all(o['enforced'] for o in job['options']))
        acl = list(yaml.safe_load_all((ROOT/'Rundeck/policies/rufus.aclpolicy').read_text()))[1]
        rule = next(r for r in acl['for']['job'] if r['equals']['uuid'] == JOB)
        self.assertEqual(rule['allow'], ['read','run'])
        inventory = yaml.safe_load((ROOT/'Ansible/inventory/compute.yml').read_text())
        macs = inventory['compute_pool']['children']['compute_macs']['hosts']
        self.assertTrue(all(not h['compute_power_control']['suspend_enabled'] for h in macs.values()))
