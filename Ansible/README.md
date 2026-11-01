# Ansible

`playbooks/debian-lxc.yml` and `roles/debian_lxc` implement the reusable Debian 13
LXC baseline. The local Proxmox transport lives in `connection_plugins/pct.py`.
Rundeck orchestrates template builds; see [LXC procedures](../docs/lxc.md).
The existing VM baseline remains in `scripts/debian-baseline.sh`.
