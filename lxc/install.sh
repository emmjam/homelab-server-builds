#!/bin/bash
# One-time administrator installation. Does not edit sudoers or run containers.
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo 'Run as root on TNAS' >&2; exit 1; }
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
DEST=/opt/homelab-lxc
for command in ansible-playbook pct pvesh pveam jq flock python3; do
    command -v "$command" >/dev/null || { echo "Missing dependency: $command" >&2; exit 1; }
done
# Root-owned installation prevents a writable Rundeck checkout being executable via sudo.
install -d -o root -g root -m 0755 "$DEST/lxc" "$DEST/Ansible"
cp -a "$SOURCE/lxc/." "$DEST/lxc/"
install -d "$DEST/Ansible/playbooks" "$DEST/Ansible/roles" "$DEST/Ansible/connection_plugins"
install -m 0644 "$SOURCE/Ansible/ansible.cfg" "$DEST/Ansible/"
install -m 0644 "$SOURCE/Ansible/playbooks/debian-lxc.yml" "$DEST/Ansible/playbooks/"
cp -a "$SOURCE/Ansible/roles/debian_lxc" "$DEST/Ansible/roles/"
install -m 0644 "$SOURCE/Ansible/connection_plugins/pct.py" "$DEST/Ansible/connection_plugins/"
chown -R root:root "$DEST"
chmod -R go-w "$DEST"
chmod 0755 "$DEST"/lxc/*.sh
printf 'Installed root-owned LXC automation in %s. Configure sudoers separately.\n' "$DEST"
