# Debian 13 LXC automation

LXC automation is independent of the VM template (9000), backup (9999), and VM scripts.
No Rufus deployment is included. Do not use container 110 for tests.

## Baseline and storage

`Ansible/roles/debian_lxc` configures Debian 13 with HTTP APT caching through
`http://192.168.0.101:3142`, HTTPS DIRECT, current packages, unattended security
updates, SSH, sudo, administration tools, en_GB.UTF-8 and Europe/London.
It adds no users, application software, QEMU agent or privileged container features.
SSH accepts keys only; root uses `prohibit-password` so an administrator can inject
an authorized public key at provisioning time without baking accounts into the template.
The template contains no authorized keys. Proxmox console access remains available.

On 1 November 2026 the supplied live cluster inventory showed `local` supports
`vztmpl` and `local-zfs` supports `rootdir`. It showed 9100 was unused. These are
build defaults, checked again at execution. `vmbr0` was verified through SSH.

## Installation and Rundeck

The administrator must install `ansible-core` on TNAS. Other dependencies are
Proxmox's `pct`, `pvesh`, `pveam`, `pvesm`, plus Python 3, jq, flock and coreutils.
The custom Ansible `pct` connection runs on TNAS and requires no SSH or Ansible
installation in the container; Python 3 is bootstrapped there.

The Rundeck job refreshes the Git checkout using the existing refresh job, stages
only LXC files at `/opt/homelab-lxc-staging`, and compares installed checksums.
It refuses to run outdated installed code. The first invocation stages files and
stops until an administrator installs them:

```sh
sudo bash /opt/homelab-lxc-staging/lxc/install.sh
```

The installer copies only LXC code into root-owned `/opt/homelab-lxc`, removing
write permission for other users. It does not edit sudoers. Use `sudo visudo -f
/etc/sudoers.d/homelab-lxc` to authorize only this entry point initially:

```sudoers
rundeck ALL=(root) NOPASSWD: /opt/homelab-lxc/lxc/build-template.sh
```

Do not authorize a user-writable checkout via sudo. Administrator installation
is deliberately required after code updates. Existing VM permissions are unchanged.

## Template procedure

```sh
sudo /opt/homelab-lxc/lxc/build-template.sh --inspect
sudo /opt/homelab-lxc/lxc/build-template.sh --template-id 9100 --storage local-zfs --image-storage local --bridge vmbr0
```

The builder selects the newest official Debian 13 standard amd64 image from
`pveam`, downloads it and creates an unprivileged candidate using a live free ID.
It applies the role twice, rejects non-idempotence, validates OS/APT/services,
network/DNS and the SSH banner, and cleans keys, machine ID, DHCP leases, logs and
random seed before shutdown. Systemd regenerates machine identity; an enabled
unit generates SSH keys before SSH on each boot (existing keys are retained).

Publication full-clones the stopped candidate into the dedicated template ID.
Only an existing template tagged `homelab-debian-lxc` may be rebuilt. A rebuild
first full-clones the old template into a new free backup ID. Backups are retained
and logged; they are never automatically pruned. If publication fails after old-ID
removal, the working backup survives at its logged ID. Inspect the failed target
before retrying; there is intentionally no blind destroy/rollback of unknown state.
The owned candidate is removed on failure or completion. Proxmox storage failures
may still require operator recovery; cleanup failures are logged. Downloaded official
images remain cached for reuse. A local flock serializes this project's LXC jobs;
Proxmox validates IDs atomically against other administrators' concurrent operations.

## Validation

```sh
python3 -m unittest discover -s tests/lxc -v
shellcheck lxc/*.sh Rundeck/scripts/invoke-lxc.sh
ANSIBLE_ROLES_PATH="$PWD/Ansible/roles" ansible-playbook -i '200,' --syntax-check Ansible/playbooks/debian-lxc.yml
ansible-lint --offline Ansible/playbooks/debian-lxc.yml Ansible/roles/debian_lxc
git diff --check
```

Offline state-machine tests simulate Proxmox and test template publication,
backup preservation and cleanup. They do not establish live guest compatibility.
Live validation requires administrator installation and sudoers configuration;
record execution URLs and guest evidence before considering the pipeline production verified.
