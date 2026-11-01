"""Exercise transfer and execution boundaries using a local fake SSH endpoint."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        self.remote = self.base / 'remote'
        self.source.mkdir()
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        for name in ['lxc', 'Ansible']:
            shutil.copytree(ROOT / name, self.source / name)
        self.key = self.base / 'key'
        self.key.touch()
        self.calls = self.base / 'calls'
        fake = self.bin / 'ssh'
        fake.write_text('''#!/usr/bin/env python3
import json,os,subprocess,sys
from pathlib import Path
command=sys.argv[-1]
with open(os.environ['CALLS'],'a') as stream: stream.write(json.dumps(command)+'\\n')
if command.startswith('sudo -n '): sys.exit(0)
result=subprocess.run(command,shell=True)
if os.environ.get('CORRUPT') and 'tar -xf' in command:
 Path(os.environ['REMOTE'],'lxc/common.sh').write_text('corrupted')
sys.exit(result.returncode)
''')
        fake.chmod(0o755)
        text=(ROOT / 'Rundeck/scripts/invoke-lxc.sh').read_text()
        text=text.replace('REPO=/opt/homelab-server-builds',f'REPO={self.source}',1)
        text=text.replace('REMOTE_REPO=/opt/homelab-server-builds',f'REMOTE_REPO={self.remote}')
        text=text.replace('KEY=/var/lib/rundeck/.ssh/target_ed25519',f'KEY={self.key}')
        text=text.replace('/tmp/homelab-lxc-dispatch.lock',str(self.base / 'lock'))
        self.script=self.base / 'dispatcher.sh'
        self.script.write_text(text)

    def run_dispatch(self,mode,**extra):
        result=subprocess.run(['bash',str(self.script),mode],env=dict(os.environ,
            PATH=f'{self.bin}:'+os.environ['PATH'],CALLS=str(self.calls),REMOTE=str(self.remote),**extra),capture_output=True,text=True)
        calls=[json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        return result,calls

    def test_transfer_only_excludes_rufus_and_never_executes_sudo(self):
        (self.source / 'Ansible/playbooks/rufus.yml').write_text('unrelated')
        result,calls=self.run_dispatch('deploy')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue((self.remote / 'lxc/build-template.sh').exists())
        self.assertTrue((self.remote / 'Ansible/roles/debian_lxc/tasks/main.yml').exists())
        self.assertFalse((self.remote / 'Ansible/playbooks/rufus.yml').exists())
        self.assertFalse(any(c.startswith('sudo ') for c in calls))

    def test_build_executes_transferred_script_after_verification(self):
        result,calls=self.run_dispatch('build',RD_OPTION_TEMPLATE_ID='9100')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(calls[-1],f'sudo -n {self.remote}/lxc/build-template.sh --template-id 9100')
        self.assertIn('sha256sum -c',calls[-2])

    def test_failed_checksum_prevents_execution(self):
        result,calls=self.run_dispatch('build',CORRUPT='1')
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(any(c.startswith('sudo ') for c in calls))

    def test_invalid_action_does_not_transfer(self):
        result,calls=self.run_dispatch('bad-action')
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(calls)

if __name__ == '__main__':
    unittest.main()
