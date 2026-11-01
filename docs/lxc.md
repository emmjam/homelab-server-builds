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

Each Rundeck job refreshes the Git checkout using the existing refresh job,
then transfers the LXC scripts, baseline role, playbook, configuration and transport
to `/opt/homelab-server-builds` on TNAS. Relative paths match Git, with entry points
under `lxc/` and configuration under `Ansible/`. Transferred files are verified
against checksums calculated from the current Rundeck checkout before execution.
There is no separate installation or manual code update step.

As with the existing VM scripts, Rundeck owns the transferred files and executes
specific entry points through sudo. Use `sudo visudo -f /etc/sudoers.d/homelab-lxc`
to add these three entries:

```sudoers
rundeck ALL=(root) NOPASSWD: /opt/homelab-server-builds/lxc/build-template.sh
rundeck ALL=(root) NOPASSWD: /opt/homelab-server-builds/lxc/create-container.sh
rundeck ALL=(root) NOPASSWD: /opt/homelab-server-builds/lxc/delete-container.sh
```

Existing VM permissions are unchanged. This follows the existing trust model:
the Rundeck account can update the code of the commands it is permitted to run.
The dispatcher serializes LXC transfer and execution on the Rundeck host.
For transfer-only verification, run `Rundeck/scripts/invoke-lxc.sh deploy` as the
Rundeck service account after refreshing the checkout. This runs no Proxmox operations.

## Template procedure

```sh
sudo /opt/homelab-server-builds/lxc/build-template.sh --inspect
sudo /opt/homelab-server-builds/lxc/build-template.sh --template-id 9100 --storage local-zfs --image-storage local --bridge vmbr0
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
Live validation requires the Ansible prerequisite and sudoers configuration;
record execution URLs and guest evidence before considering the pipeline production verified.

## Container lifecycle

The three sudoers entries above cover all lifecycle operations.

Create a container (ID 9200 is an example; availability is checked live):

```sh
sudo /opt/homelab-server-builds/lxc/create-container.sh \
  --id 9200 --hostname debian-lxc-test --cores 2 --memory 1 --disk 8 \
  --storage local-zfs --bridge vmbr0 --ip dhcp --dns '192.168.0.2' \
  --template-id 9100
```

For static IPv4, supply `--ip 192.168.0.220/24 --gateway 192.168.0.1`, after
reserving that address in the network's DHCP configuration. Optional flags are
`--search-domain lan` and `--ssh-public-key 'ssh-ed25519 AAAA... comment'`.
Only one public key without authorized_keys options is accepted. No user account
is created. Without a key, use `pct enter ID` for administration; the SSH listener
is checked but SSH login is unavailable. IPv6-only provisioning is not implemented.

Creation requires an unused numeric ID, a unique hostname and a managed baseline
template. It makes a full clone with a fresh locally administered MAC, applies
resource and network settings, grows the root disk, starts the guest, optionally
installs the supplied root public key, and verifies hostname, resources, routing,
DNS, SSH banner, Debian baseline and regenerated identity. RAM and disk use whole
GB at the interface (RAM is converted to MiB for Proxmox). Disk shrinking is refused.
A post-clone failure cleans up only the container created by that invocation.
If the clone command itself fails, Proxmox performs its clone rollback; any unknown
remaining target is left for inspection rather than blindly destroyed.

Delete a container:

```sh
sudo /opt/homelab-server-builds/lxc/delete-container.sh --id 9200 --confirm DELETE-9200
```

Deletion accepts only a numeric ID and exact ID-specific confirmation. It refuses
Proxmox templates, an existing Proxmox protection flag, and infrastructure ID 110.
There is no added Plex ID protection and no changes are made to existing protection
flags. A running container must shut down cleanly within 60 seconds. Failure to
stop aborts deletion; there is no forced-stop fallback. Protection and stopped
state are checked immediately before destroying that ID. VM deletion behaviour
is unchanged.

Git-managed jobs:

| Job | UUID |
|---|---|
| Proxmox - Build Debian LXC Template | `ad03d069-5b55-477b-bf75-27d85a04e8a3` |
| Proxmox - Create LXC Container | `30105ab1-cc4e-46ca-9fd6-15a3ddcf8a48` |
| Proxmox - Delete LXC Container | `52b08d85-d1fc-48c6-8bbd-04a69db365aa` |

Use these jobs directly: they expose validated options and invoke the shared
`Rundeck/scripts/invoke-lxc.sh` dispatcher. Each refreshes Git, transfers the required LXC files to TNAS, verifies their
checksums, then executes the requested operation through sudo.

## Validation record (1 November 2026)

- Stage 1: five offline state-machine tests passed before lifecycle implementation.
- Combined: fifteen offline tests cover template builds, retained backups, malformed
  parameters, MAC/resource settings, clone cleanup, confirmation, templates,
  protected containers and clean shutdown failures.
- Ansible syntax check and ansible-lint passed. The custom transport also passed
  actual Ansible ping/module execution and file-copy tests using an isolated fake
  pct executable under `/tmp`; no guest or host baseline was changed by that test.
- ShellCheck passed for new LXC scripts and the dispatcher. Bash syntax passed
  for every existing shell script as well as the new scripts. Existing VM files
  are unchanged. Existing VM baseline ShellCheck reports its pre-existing unused
  `attempt` variable; no unrelated VM changes were made to silence it.
- All Rundeck YAML parses and all job IDs match their UUIDs and managed groups.
- Initial live setup execution [131](http://192.168.0.51:4440/project/HomeLab/execution/show/131)
  confirmed checkout refresh/job import, then failed before container operations
  because `/opt` staging was not writable. The separate installation design was
  subsequently removed; jobs now transfer into the established TNAS checkout.
- Live template, clone, identity uniqueness, SSH login, deletion and VM functional
  regression tests remain pending sudoers setup. No production
  container or VM was changed during these checks.

CLI flags were checked against the upstream [Proxmox pct reference](https://github.com/proxmox/pve-docs/blob/master/generated/pct.1-synopsis.adoc).

The deployment-pattern revision adds four dispatcher tests: transfer-only operation,
verification before execution, rejection of corrupted transfers, and rejection of
unknown actions. Transfer-only mode excludes unrelated playbooks, including Rufus.
