"""Local Proxmox pct transport. Inventory hosts are numeric container IDs."""
from __future__ import annotations
import os
import subprocess
from ansible.errors import AnsibleConnectionFailure
from ansible.plugins.connection import ConnectionBase

DOCUMENTATION = r"""
name: pct
short_description: Execute Ansible through the local Proxmox pct command
description:
  - Inventory hosts must be numeric container IDs on the current Proxmox node.
author: Homelab
extends_documentation_fragment:
  - connection_pipelining
"""

class Connection(ConnectionBase):
    transport = 'pct'
    has_pipelining = True

    def _connect(self):
        if not str(self._play_context.remote_addr).isdigit():
            raise AnsibleConnectionFailure('pct requires a numeric container ID')
        self._connected = True
        return self

    def exec_command(self, cmd, in_data=None, sudoable=True):
        super().exec_command(cmd, in_data=in_data, sudoable=sudoable)
        self._connect()
        process = subprocess.Popen(
            ['/usr/sbin/pct', 'exec', str(self._play_context.remote_addr),
             '--', '/bin/sh', '-c', cmd],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(in_data)
        return process.returncode, stdout, stderr

    def put_file(self, in_path, out_path):
        super().put_file(in_path, out_path)
        self._connect()
        result = subprocess.run(['/usr/sbin/pct', 'push',
            str(self._play_context.remote_addr), in_path, out_path], capture_output=True)
        if result.returncode:
            raise AnsibleConnectionFailure(result.stderr.decode(errors='replace'))

    def fetch_file(self, in_path, out_path):
        self._connect()
        result = subprocess.run(['/usr/sbin/pct', 'pull',
            str(self._play_context.remote_addr), in_path, os.path.abspath(out_path)], capture_output=True)
        if result.returncode:
            raise AnsibleConnectionFailure(result.stderr.decode(errors='replace'))

    def close(self):
        self._connected = False
