"""Run Ansible on Rundeck, reaching the active build guest through TNAS SSH."""
from __future__ import annotations
import base64
from pathlib import Path
import shlex
import subprocess
from ansible.errors import AnsibleConnectionFailure
from ansible.plugins.connection import ConnectionBase

DOCUMENTATION = r"""
name: pct
short_description: Reach the temporary Proxmox build guest from Rundeck
description:
  - Uses the existing Rundeck SSH key to reach TNAS.
  - The sudo build entry point restricts commands to its active temporary guest.
author: Homelab
extends_documentation_fragment:
  - connection_pipelining
"""

class Connection(ConnectionBase):
    transport = 'pct'
    has_pipelining = True

    def _connect(self):
        if not str(self._play_context.remote_addr).isdigit():
            raise AnsibleConnectionFailure('pct requires a numeric build container ID')
        self._connected = True
        return self

    def _run(self, command, data=None):
        self._connect()
        encoded = base64.b64encode(command.encode()).decode()
        remote = ('sudo -n /opt/homelab-server-builds/scripts/build-template.sh '
                  f'--ansible-exec {self._play_context.remote_addr} {encoded}')
        process = subprocess.Popen(
            ['ssh', '-T', '-i', '/var/lib/rundeck/.ssh/target_ed25519',
             '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
             '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
             'rundeck@192.168.0.101', remote],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(data)
        return process.returncode, stdout, stderr

    def exec_command(self, cmd, in_data=None, sudoable=True):
        super().exec_command(cmd, in_data=in_data, sudoable=sudoable)
        return self._run(cmd, in_data)

    def put_file(self, in_path, out_path):
        super().put_file(in_path, out_path)
        # Transfer bytes through stdin; neither filenames nor file content become
        # executable host shell syntax. The shell runs only in the build guest.
        rc, _, stderr = self._run('umask 077; cat > ' + shlex.quote(out_path), Path(in_path).read_bytes())
        if rc:
            raise AnsibleConnectionFailure(stderr.decode(errors='replace'))

    def fetch_file(self, in_path, out_path):
        rc, stdout, stderr = self._run('cat -- ' + shlex.quote(in_path))
        if rc:
            raise AnsibleConnectionFailure(stderr.decode(errors='replace'))
        Path(out_path).write_bytes(stdout)

    def close(self):
        self._connected = False
