# Ansible

`playbooks/debian-lxc.yml` and `roles/debian_lxc` implement the reusable Debian 13
LXC baseline. Ansible runs on Rundeck. The SSH-mediated Proxmox transport lives in `connection_plugins/pct.py`.
Rundeck orchestrates template builds; see [LXC procedures](../docs/lxc.md).
The existing VM baseline remains in `scripts/debian-baseline.sh`.

HP inference adoption uses `playbooks/ai-inference.yml`, role `ollama_inference`
and `inventory/ai-inference.ini`. It retains the approved installed runtime/model
and derives the sole allowed client IPv4 from the verified Rufus inventory host.
See [AI1 deployment and validation](../docs/ai-inference.md).
