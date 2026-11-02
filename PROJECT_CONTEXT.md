# Homelab Project Context

**Last updated:** 31 October 2026  
**Repository:** `emmjam/homelab-server-builds`  
**Branch:** `main`  
**Primary purpose:** Maintain the authoritative technical context for the homelab infrastructure, automation, and development roadmap.

---

# 1. Instructions for AI Coding Agents

This document provides the background necessary to work on this homelab project.

Before making changes:

1. Read this document in full.
2. Inspect the current GitHub repository and relevant scripts.
3. Treat the actual configuration and scripts as the source of truth for implementation details.
4. Distinguish confirmed functionality from planned functionality.
5. Do not assume a proposed feature has already been implemented.
6. Do not overwrite working functionality without understanding its purpose.
7. Prefer complete, maintainable and idempotent scripts.
8. Test changes wherever practical.
9. Explain what has changed and identify any outstanding issues.
10. Update this document when significant architectural decisions or infrastructure changes are made.

**Important:** Do not invent configuration, credentials, paths, or implementation details. Where something is uncertain, inspect the system or ask for clarification.

# 2. Overall Architecture

The homelab is built around a TerraMaster F4-424 Pro running Proxmox VE.

The TNAS provides the primary virtualisation platform and hosts infrastructure services.

The longer-term architecture includes:

- Proxmox virtual machines for infrastructure services.
- Debian-based server templates.
- GitHub for version-controlled scripts and configuration.
- Rundeck for controlled automation.
- Pi-hole for DHCP and DNS.
- A dedicated local AI management system called Rufus.
- Additional physical machines for development, AI workloads and distributed processing.

The general principle is to automate repeatable infrastructure deployment through scripts and Rundeck rather than performing manual configuration.

Local AI responsibilities are split across three machines: TNAS/Rufus manages and coordinates workloads; the HP/`ai-agent.lan` provides primary interactive inference; and the Dell/`ai-worker.lan` handles background agents, parallel processing and additional AI workloads. Keep management independent of inference so the compute machines can be started, stopped, maintained or reassigned without losing central coordination.

## Separate media-library project: Bobarr and Plex

Bobarr is intended to manage a self-hosted film and television media library, with that library feeding into Plex for media playback. Bobarr is a separate homelab project; it is not part of Rufus or the Rundeck automation infrastructure. The project reference is [Bobarr](https://github.com/iam4x/bobarr). Deployment choices and integrations beyond this relationship have not been finalised.

# 3. Primary Infrastructure: TNAS

## Hardware

| Component | Specification |
|---|---|
| Device | TerraMaster F4-424 Pro |
| CPU | Intel i3-N305 |
| CPU cores | 8 |
| RAM | 32 GB |
| SATA storage | 4 × 4 TB |
| NVMe storage | 2 × 1 TB |

## Operating environment

- Proxmox VE 9.2.21
- Kernel 7.0.2-6-pve
- ZFS storage

The user refers to the system as TNAS, not TOS.

## Storage

| Storage | Purpose |
|---|---|
| `rpool` | NVMe mirrored ZFS pool |
| `tank` | SATA mirrored ZFS pool |
| `local-zfs` | Proxmox VM storage |
| `tank` | General data and shared storage |
| `local` | Proxmox local storage |
| `iso-dir` | ISO directory storage |

Important paths:

- `/tank/data/shared/ISO`
- `/tank/data/template/iso`
- `/var/lib/vz`

**ISO storage decision:**

ISOs must be stored in:

`/tank/data/shared/ISO`

Proxmox uses a symlink:

`/tank/data/template/iso`

Do not move the actual ISO collection into Proxmox's standard nested ISO directory.

## Networking

| Interface | Address | Purpose |
|---|---|---|
| vmbr0 | 192.168.0.101/24 | Primary network |
| vmbr1 | 192.168.0.102/24 | Secondary network |

- Default gateway: `192.168.0.1`
- Primary physical interface: `nic0`
- Secondary physical interface: `nic1`
- Both interfaces are bridged independently.
- No bonding is configured.

## Temperature protection

Existing script:

`/root/scripts/tnas-temperature-guard.py`

Runs through a systemd timer every minute.

Configured thresholds:

| Component | Warning | Shutdown |
|---|---:|---:|
| CPU | 85°C | 95°C |
| NVMe | 60°C | 65°C |
| HDD | 50°C | 60°C |

Hysteresis: 3°C.

Future improvement: include the three highest CPU-consuming processes in high-temperature logs.

# 4. Network Infrastructure

## Router and DNS

| Device | Address | Purpose |
|---|---|---|
| Vodafone router | 192.168.0.1 | Router and gateway |
| Pi-hole | 192.168.0.2 | DHCP and DNS |
| TNAS | 192.168.0.101 | Proxmox |
| TNAS secondary | 192.168.0.102 | Secondary interface |

Pi-hole now provides DHCP and DNS.

The Vodafone router provides Wi-Fi using the same SSID and password as previously configured.

## Secure external media-library access

Provide password-protected web access to the media directory through `emmjam.linkpc.net`. The proposed deployment uses a dedicated Debian VM, Nginx as the web server and reverse proxy, and Certbot to obtain and maintain HTTPS certificates. Nginx is also intended to reverse-proxy Bobarr.

HTTPS and authentication are required for external access. Do not expose the media directory or Bobarr interface publicly without appropriate access controls. Exact VM details, proxy configuration, and authentication implementation remain undecided.

## Future DNS improvements

Planned:

- Unbound recursive DNS.
- DNSSEC.
- Encrypted DNS.
- Improved DHCP management interface.
- Reliable hostname registration for provisioned VMs.

## DHCP hostname registration

Planned improvement to the Debian client provisioning process:

At boot, each provisioned Debian client should:

1. Obtain its final hostname.
2. Obtain its active DHCP IP address.
3. Query Pi-hole directly at `192.168.0.2` using `dig`.
4. Compare the returned DNS address with its current IP.
5. Do nothing if the registration is correct.
6. If missing or incorrect, renew the DHCP lease using `dhclient`.
7. Retry the DNS check.
8. Log the outcome.

**Implementation decision:** This functionality belongs in the provisioned VM configuration, not in the Debian template.

The template should remain generic.

# 5. GitHub Repository

Repository:

`https://github.com/emmjam/homelab-server-builds`

Branch: `main`

The repository is the source of truth for infrastructure build scripts.

Rundeck should retrieve the latest scripts from GitHub whenever a build job runs.

Previously identified scripts include:

- `scripts/debian-baseline.sh`
- `scripts/provision-vm.sh`
- `scripts/rebuild-debian-template.sh`
- `scripts/rundeck_build.sh`

Always inspect the current repository before assuming these files retain their previous implementation.

Last observed repository commit: `423e09d`.

## Development principles

- Version control all scripts.
- Prefer parameterised scripts.
- Avoid hardcoded VM configuration.
- Make scripts idempotent wherever practical.
- Handle errors explicitly.
- Use meaningful exit codes.
- Provide useful execution logs.
- Keep secrets outside GitHub.
- Document configuration and dependencies.

# 6. Debian VM Template

## Current design

The preferred deployment foundation is a Debian 13 cloud-init VM template.

PXE-based deployment is not currently the primary VM provisioning method.

Known template details:

| Setting | Value |
|---|---|
| VM ID | 9000 |
| Name | debian-13-template |
| CPU | 2 cores |
| RAM | 2048 MB |
| Disk | 3 GB |
| Storage | local-zfs |
| Cloud-init user | ian |
| Network | DHCP |
| QEMU agent | Enabled |

Additional VM IDs previously used:

| VM ID | Purpose |
|---|---|
| 9998 | Candidate template |
| 9999 | Backup template |

The backup template is named `debian-13-template-backup`.

These IDs should be verified against Proxmox before making changes.

## Debian baseline

The baseline script is responsible for preparing a standard Debian VM.

Existing functionality includes:

- Creation of the `rundeck` account where required.
- SSH key configuration.
- Passwordless sudo configuration.
- General Debian baseline preparation.

The script contains an existence check for the `rundeck` account.

Do not unnecessarily reimplement this functionality.

## APT configuration

The dedicated Apt-Cache VM on TNAS provides the APT caching proxy at:

`http://apt-cache:3142`

Verified 1 November 2026: VM 112, 2 cores, 2 GB RAM, 64 GB total disk,
DHCP address `192.168.0.116`. Ansible manages apt-cacher-ng, daily expiration
and hourly disk monitoring; see `docs/apt-cache.md`. Future conversion to an
LXC with TNAS-backed storage is CACHE-01 in `BACKLOG.md`.

HTTPS Debian APT traffic should go directly to the repositories rather than through the HTTP caching proxy.

The working configuration uses:

`Acquire::https::Proxy="DIRECT"`

# 7. VM Provisioning

The provisioning process should follow this architecture:

1. Rundeck starts the job.
2. Rundeck obtains the latest scripts from GitHub.
3. Scripts are transferred to TNAS.
4. TNAS executes the provisioning operations through the Proxmox API or local Proxmox commands, as appropriate.
5. A VM is cloned from the Debian template.
6. VM resources are configured.
7. The VM starts and cloud-init completes.
8. Provisioning tasks are executed.
9. The job reports success or failure.

## Provisioning parameters

The provisioning script must support configurable:

- VM ID.
- VM name.
- CPU cores.
- RAM in GB.
- Disk size.

**Important:** The memory parameter is expected in GB, not MB.

The long-term requirement is for Rufus to invoke VM creation with different resource parameters without requiring changes to the provisioning script.

Do not replace parameterisation with fixed VM specifications.

# 8. Rundeck Automation

## Current installation

Rundeck version:

`6.3.0-20261022`

Rundeck is intended to be the central automation interface for infrastructure operations.

## GitHub integration

The Rundeck host has a working checkout at:

`/opt/homelab-server-builds`

The checkout should be updated from GitHub for each execution rather than relying on a permanently stale local copy.

Previous Git ownership and `safe.directory` issues were resolved.

## SSH access to TNAS

Target:

`rundeck@192.168.0.101`

A temporary SSH key pair was previously deployed under:

`/var/lib/rundeck/.ssh/target_ed25519`

The corresponding public key was also created.

The last reported copy-to-TNAS job succeeded after changing SSH execution to Bash.

The user also has a previous temporary key pair under:

`/home/ian/rundeck-setup/target_ed25519`

This is intended for later cleanup.

Do not assume temporary keys have already been removed.

## Proxmox API

API user:

`rundeck@pve`

Token name:

`rundeck-automation`

Role:

`RundeckVMAdmin`

Permissions were configured on:

- `/vms`
- `/storage/local-zfs`

The missing `SDN.Use` permission was previously identified and corrected.

The Proxmox clone API test subsequently succeeded.

Secrets must remain in Rundeck Key Storage or another appropriate secrets store.

Relevant Key Storage paths include:

- `HomeLab/rundeck_ssh_key`
- `HomeLab/rundeck_ssh_key_pub`
- Proxmox credentials under `HomeLab/keys/proxmox/`

Never put actual tokens, passwords or private keys in this document or GitHub.

## Outstanding Rundeck improvements

### Standardised privileged execution

Implement a controlled method for executing privileged scripts on TNAS.

Proposed fixed temporary script path:

`/opt/homelab-server-builds/scripts/rundeck-task.sh`

Requirements:

- Rundeck overwrites the same fixed path for each task.
- A single narrowly scoped NOPASSWD sudoers rule permits execution.
- Ownership and permissions prevent unsafe replacement.
- Execution captures the actual exit status.
- Temporary scripts are reliably deleted afterwards.
- Cleanup must happen on success, failure and interruption wherever possible.

Do not introduce unrestricted passwordless sudo.

### Job definitions in GitHub

Rundeck job definitions should be version-controlled alongside the build scripts.

Avoid maintaining the only copy of important job definitions in the Rundeck UI.

### Execution logging

Investigate why Rundeck executions currently show job status but do not consistently expose useful job-step output.

Ensure scripts provide visible, meaningful output and preserve exit status.

### Wake-on-LAN

The controlled Rundeck job accepts an allowlisted host and wake/sleep action. Sleep and wake were tested successfully on both AI hosts. The AI-mgmnt VM can invoke the job; persistence across host reboots has not been verified.

# 9. Physical Machines

## HP EliteDesk 800 G3 DM

| Component | Specification |
|---|---|
| CPU | Intel i5-6500T |
| Cores / threads | 4 / 4 |
| RAM | Upgrade completed; capacity not recorded |
| SSD | 120 GB |
| DHCP/DNS hostname | `ai-agent.lan` |

The BIOS issue was resolved and the RAM and SSD upgrades completed.

**Role:** Primary AI agent and local inference machine. It hosts the primary local AI model and handles interactive inference and conversational workloads for the homelab.

The host should support suspend-to-RAM and Wake-on-LAN for on-demand availability.

## Dell OptiPlex mini

| Component | Specification |
|---|---|
| CPU | Intel i3-4160T |
| RAM | 8 GB |
| Storage | 1.8 TB HDD |
| Networking | Active interface `enp2s0` uses the Realtek `r8169` PCI driver |
| DHCP/DNS hostname | `ai-worker.lan` |

**Role:** AI worker for background agents and tasks, parallel processing, and additional independent AI workloads. This keeps background processing separate from the HP's primary interactive workload.

The USB RTL8153 network adapter was trialled and removed. The active `enp2s0` interface supports magic-packet WOL; suspend and wake have been tested through Rundeck.

## Mac Pros

Two identical Mac Pros are available.

- Ubuntu 20 installations have previously been used for backup purposes.
- One may be used as a Proxmox development/test machine.
- They may provide additional AI compute resources.

The exact specifications should be inspected before assigning workloads.

## Raspberry Pi

Dedicated to Pi-hole.

Do not assume it is available for unrelated workloads.

# 10. Rufus: Local AI Management System

The local AI management system is called:

**Rufus**

The underlying VM/service name may remain `AI-mgmnt`.

Rufus runs on TNAS as the central AI management and orchestration system. It is intended to remain available as the coordinator. Keep management and orchestration separate from inference; TNAS is not the primary interactive inference machine.

Rufus coordinates the AI environment across the HP and Dell. It determines where workloads should run and can move routine work to the Dell when the HP is busy. Its intended capabilities include:

- Understand the homelab architecture.
- Query infrastructure information.
- Use Rundeck jobs, pipelines and other operations available through its API for infrastructure and VM management. Presence in Rundeck is the approval boundary.
- Coordinate work across the AI agent and worker rather than assuming all work runs locally.
- Start, stop, maintain or reassign compute workloads without losing central orchestration.
- Monitor infrastructure health.
- Coordinate local AI workloads.
- Use external AI services when available.

## AI architecture

The user wants a hybrid AI architecture.

The intended arrangement is:

- Use online AI services such as ChatGPT when available and appropriate.
- Fall back to locally hosted AI when online services or available usage are unavailable.
- Use local agents to retrieve information and perform infrastructure tasks.
- Allow local agents to supply relevant information to the reasoning model.

## Model management

Only one AI model/AI VM should run at a time on each compute machine.

Initial planned models:

- Qwen 3 4B.
- Gemma.

Machine responsibilities:

| Machine | Logical role | Responsibility |
|---|---|---|
| TNAS / Rufus (`AI-mgmnt`) | Management and orchestration | Always-available coordination and workload placement; not primary interactive inference |
| HP EliteDesk (`ai-agent.lan`) | Primary AI agent | Primary local model, interactive inference, and conversational workloads |
| Dell OptiPlex (`ai-worker.lan`) | AI worker | Background agents, parallel processing, and additional independent AI workloads |

Separate AI VMs should be available but remain stopped by default. The deployment mode for the HP and Dell (bare-metal Linux, Proxmox, or AI workloads in VMs) has not been decided; do not assume one.

AI-mgmnt/Rufus must remain a dedicated AI management system, not be combined with Rundeck.

# 11. PXE Infrastructure

PXE is a future infrastructure capability.

The preferred approach is:

- Pi-hole DHCP options configured for PXE.
- On-demand iVentoy as the initial implementation.
- PXE Boot0r as an alternative to investigate.

The shared ISO location remains:

`/tank/data/shared/ISO`

PXE should not become a dependency for the existing Debian cloud-init provisioning workflow.

# 12. Outstanding Technical Backlog

The following items represent known work or future improvements. They are not necessarily implemented.

## High priority

1. Verify and consolidate the Debian provisioning scripts.
2. Complete the AI interface, agent and worker nodes deployment.

## Medium priority

3. Improve Pi-hole DNS with Unbound and DNSSEC.
4. Improve DHCP management usability.
5. Implement the PXE infrastructure.
6. Improve TNAS temperature logging.
7. Review existing testing to see whether checks can be amalgamated into single scripts that return clear exit/status codes and concise output, reducing agent token use while retaining useful failure diagnostics.

## Longer term

7. Implement a Debian gateway.
8. Investigate standby gateway HA/failover.
9. Implement a separate NordVPN/Squid proxy VM.
10. Develop the hybrid online/local AI architecture.
11. Integrate Rufus with infrastructure monitoring and automation.
12. Expand distributed AI computing across available machines.

# 13. Networking and Security Principles

- Keep the primary gateway available independently of optional VPN services.
- VPN failure must not cause a general network outage.
- Selected traffic should be able to use the VPN proxy.
- Vodafone connectivity remains the fallback.
- Keep infrastructure services separated where practical.
- Store credentials in secrets management systems.
- Use restricted service accounts.
- Avoid unrestricted sudo permissions.
- Ensure automation failures are visible.
- Avoid hardcoding credentials in scripts.

# 14. Working Preferences and Development Rules

The user has several explicit preferences that should guide all development.

## Communication

- Use British English.
- Be direct and technically precise.
- Do not repeat diagnostic requests when the relevant configuration has not changed.
- Use hostnames for SSH and SCP wherever possible so DHCP and hostname-registration failures are quickly recognised; investigate hostname failures rather than silently substituting an IP address.
- Do not assume the user is in India.
- Do not introduce unrelated architectural alternatives without a good reason.
- Respect previous decisions unless there is a technical reason to revisit them.

## Technical work

- Prefer complete scripts rather than isolated replacement snippets.
- Inspect the current implementation before proposing modifications.
- Avoid unnecessary changes to working components.
- Make scripts idempotent.
- Preserve existing functionality.
- Test before declaring a change successful.
- Do not claim an operation succeeded until its result has been verified.
- Clearly distinguish recommendations from implemented changes.
- Whenever directives are updated, immediately commit and push those directive changes to Git. This is standing authorisation for directive updates; keep unrelated changes out of those commits.
- Allocate template IDs using the next available ID counting upwards from 9000. Allocate backup template IDs using the next available ID counting downwards from 9999. Allocate VM and container IDs using the next available ID counting upwards from 100. Check the shared Proxmox guest-ID namespace before allocation. This supersedes earlier fixed-ID allocation instructions; existing guests require an explicitly authorised migration before renumbering.
- Leave the Rundeck host's secrets file ownership and permissions as set by the user; do not change them unless explicitly instructed.

## Architecture

- GitHub is the source of truth for scripts.
- Rundeck is the automation execution layer.
- Proxmox is the virtualisation layer.
- TNAS is the primary infrastructure host.
- Rufus on TNAS is the central AI management and orchestration layer; the HP and Dell provide inference capacity in their agreed agent and worker roles.

Do not combine these responsibilities unnecessarily.

# 15. Change Management

When completing significant work:

1. Inspect the current repository.
2. Identify the files and dependencies affected.
3. Explain the proposed changes.
4. Implement the changes.
5. Test the result.
6. Report the actual test results.
7. Update this document if architecture, configuration or implementation status has changed.
8. Commit changes only when authorised.

Keep the distinction between:

- **Implemented:** Verified to work.
- **In progress:** Partially implemented.
- **Planned:** Agreed but not implemented.
- **Under investigation:** Requires further technical assessment.
- **Retired:** No longer part of the architecture.

This document should evolve with the infrastructure and remain a reliable source of project context for future AI-assisted development.

## Debian LXC automation (1 November 2026)

Current Rufus application status (1 November 2026): fresh CT 111, hostname
`rufus`, DHCP `192.168.0.52`, is operational with the authenticated loopback API.
Real Rundeck health-check execution 157 succeeded through Rufus, independent
policy rejection passed, and execution tracking survived a service restart.
The complete post-acceptance suite passed 55 tests. Rundeck's one-year token
limit and restricted Rufus ACL are managed by Ansible; the restricted token
expires 1 November 2027 at 19:16:07 UTC and its predecessor was revoked.
See `Rufus/README.md` for the acceptance record. Earlier addresses below are
historical validation results, not the current Rufus address.

A separate Debian 13 LXC baseline and lifecycle implementation now lives under
`Rundeck/scripts/`, `Ansible/roles/debian_lxc` and `Ansible/playbooks/debian-lxc.yml`.
The planned template ID is 9100, confirmed unused in the supplied live inventory
and rechecked at runtime. Defaults use `local` for official image downloads,
`local-zfs` for root disks and `vmbr0` for networking. VM automation is unchanged.
See `docs/lxc.md` for Git-managed transfer and execution, the three Rundeck jobs,
parameters, retained template backups and testing procedures. Ansible runs on the
Rundeck controller; TNAS executes only the Proxmox operations through the transferred
LXC scripts. Template build 141 and creation 142 succeeded; template 9100 and
new Rufus CT 111 are present. The user removed old Rufus CT 110. The Rufus
provisioning playbook was separately run from Rundeck with no failures; it prepares
accounts and dependencies only, not an application/service. Rebuild, deletion and
remaining lifecycle validation are still outstanding; see `docs/lxc.md`.

Temporary local credentials are held in `/home/ian/Projects/CRAP/secrets.txt`
with mode 0600, outside this repository, pending a dedicated secrets solution.
That file and its backups must never be committed. Existing operational SSH key
files remain in place; the local file holds copies for the later migration.

Rundeck API-calling scripts read `RUNDECK_TOKEN` from `/tmp/secrets.txt` on the
Rundeck host. The local laptop's `CRAP/update_secrets.sh` transfers the file and
sets owner `rundeck:rundeck` and the user-requested temporary mode 0777. `GITHUB_TOKEN` may also be supplied there;
otherwise Git refresh retains the existing GitHub Key Storage option. Existing
Rundeck SSH key files and authentication paths remain unchanged.

## Permanent testing and validation directive

During builds, run a check only when its output is required by a subsequent
step or to establish that a change affected another component. Use command exit
codes as success indicators; do not issue a second command merely to confirm the
first ran successfully. Put final end-to-end validation in one script and execute
it with one SSH call. Use Rundeck WOL to wake any machines needed. This directive
supersedes earlier instructions to run routine suites during intermediate builds.

## Permanent host availability / WOL directive

Some compute nodes intentionally sleep or power down when idle. Before
investigating SSH, networking, DNS, services, authentication or similar connection
failures, establish whether the managed target is awake and reachable. Treat an
asleep/offline WOL-capable node as a normal availability state. Use the approved
WOL mechanism where appropriate and wait for network/SSH availability before
configuration-level troubleshooting. If waking cannot be verified, report
unresolved availability rather than assuming a configuration fault. Do not
modify working SSH/network configuration merely because a sleeping or powered-down
node is unreachable.

Rufus's eventual worker-management and diagnostic logic must follow the same
availability-first sequence and distinguish sleeping/unavailable workers from
configuration faults. HP/Dell wake uses the existing **HomeLab - AI Host Power**
Rundeck job (`7d9a3328-c8df-4e31-bbf6-49a6d9ce5a11`) with `action=wake` and the
allowlisted hostname. A sent packet is not verified wake; failed hostname-based
verification is not by itself proof of failed hardware wake. See `AGENTS.md`.

## HP inference / AI1 acceptance — 2 November 2026

The existing HP installation is now managed by
`Ansible/playbooks/ai-inference.yml`, role `ollama_inference`, through Rundeck job
**HomeLab - Deploy HP Inference** (`0b42e662-1cce-49ec-a43e-7345db516937`).
Retained runtime: Ollama 0.40.13; model: `qwen3:4b` Q4_K_M. No runtime reinstall,
model download or GPU-driver change was needed. Hardware verified: i5-6500T,
four cores/threads, 7824 MiB RAM, Intel HD 530, 91 GiB root space free.

HP endpoint is `http://ai-agent.lan:11434` (currently `192.168.0.118`). A dedicated
nftables table allows only the verified inventory Rufus IPv4 remotely (currently
`192.168.0.52/32`) and local HP checks; other traffic to this port is dropped.
The enabled firewall service is required before Ollama starts. Rufus remains
unprivileged, its own API remains loopback-only and it receives no infrastructure
SSH keys. Client/settings: `/opt/rufus/app/inference.py` and
`/opt/rufus/config/inference.json`.

Acceptance execution [171](http://192.168.0.51:4440/project/HomeLab/execution/show/171)
passed real structured inference as Rufus, local inference, enabled/active
services, controller denial and safe unavailable-backend errors. Second deployment
reported zero changes on all hosts. Shared repository validation: 67 tests and
shell syntax passed. No AI1 reboot was performed. LAN inference is source-IP
restricted HTTP, without TLS/application authentication, as approved. See
`docs/ai-inference.md` for exact model digest, procedures and acceptance evidence.
AI1 is complete; AI2 passed approved repair 188 and independent verification 189; disposable fixture removed by cleanup 191 (see `docs/ai2-api.md`). Long-sleep DHCP/DNS recovery remains a
separate investigation; the approved short suspend/WOL cycle passed 167/168.
