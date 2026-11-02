# Authoritative homelab project backlog

**Updated:** 1 November 2026

**Repository:** `emmjam/homelab-server-builds`

**Shared by:** Codex and ChatGPT

This is the canonical project backlog. Maintain priorities, dependencies, statuses
and completion evidence here. It supersedes the backlog and task-status lists in
older documentation, including section 12 of `PROJECT_CONTEXT.md`. That document
remains infrastructure context; scripts and job definitions establish actual behaviour.

This initial reconciliation inspected the repository through `bb21a2b`, its Git
history, documentation, scripts, Ansible files, Rundeck definitions and TODO/FIXME
searches. No backlog item was implemented while creating this file. Repository
visibility, token usage in GitHub and current deployed infrastructure were not
reverified for this documentation change.

## Status and ordering rules

- **TODO:** agreed or explicitly documented work not completed.
- **IN PROGRESS:** implementation exists, but the stated outcome is incomplete.
- **BLOCKED:** remaining work has a specific unresolved prerequisite.
- **DONE:** the stated scope is supported by tracked implementation or recorded
  validation. Code completion does not establish an unperformed live test.

Use the IDs below when updating work. Record evidence before marking an item DONE.
Keep completed entries rather than recreating them as new tasks.

**Delivery order:** finish the current LXC foundation and its prerequisites, make
basic Rufus work, then immediately deliver Rufus VS Code integration. OpenBao
comes after both Rufus and the VS Code work. GitHub/Rundeck security and existing
operational maintenance are separate tracks; scheduling them must not displace
VS Code as the immediate follow-on to basic Rufus. The remaining infrastructure
roadmap is queued below those commitments, without an invented delivery date.

Creating this backlog authorises documentation only. It does not authorise
implementation, repository visibility changes, credential changes or deployments.
Preserve the existing working Git and Rundeck SSH setup until its relevant work
is explicitly started. Never commit tokens, passwords, private keys or secrets files.

## P0 — Finish the current Debian LXC foundation

| ID | Status | Work and completion criteria | Evidence / dependency |
|---|---|---|---|
| LXC-01 | DONE | Implement the separate Debian 13 LXC baseline, template builder, parameterised creation and confirmed deletion scripts, Git-managed jobs and offline tests. This entry covers implementation only. | [LXC procedures](docs/lxc.md), [scripts](Rundeck/scripts/), [baseline role](Ansible/roles/debian_lxc/), [tests](tests/lxc/); commits `4c55446`, `ff4b7de`, `7ab0f3a`, `ad963fb`. |
| LXC-02 | IN PROGRESS | Complete live template build/rebuild, disposable cloning, resources, hostname/network/DNS, SSH login, baseline/APT proxy and HTTPS DIRECT checks, machine-ID/host-key uniqueness, deletion guards, failure cleanup and VM regression checks. Record execution links and actual results. | [Validation record](docs/lxc.md#validation-record-1-november-2026). Template build [141](http://192.168.0.51:4440/project/HomeLab/execution/show/141) and new Rufus CT 111 creation [142](http://192.168.0.51:4440/project/HomeLab/execution/show/142) succeeded. Template baseline passed twice with an unchanged second run; temporary candidate 101 was removed. Rebuild/backup, cross-clone identity, deletion and VM regression checks remain outstanding. |
| LXC-03 | DONE | Apply and verify the three narrowly scoped LXC sudo permissions on TNAS. | All three flat `scripts/` entry points passed `sudo -n -l` on 1 November 2026; live build and creation succeeded through Rundeck. |

Preserve existing production guests during all disposable tests. The user removed
the old Rufus CT 110; newly provisioned Rufus is CT **111**. Keep VM and LXC operations separate. Ansible runs on Rundeck;
Rundeck refreshes Git and transfers the required scripts to TNAS when needed.

## P1 — Basic Rufus

| ID | Status | Work and completion criteria | Evidence / dependency |
|---|---|---|---|
| RUFUS-01 | DONE | Deterministic Rufus API discovers approved jobs, validates parameters, submits and tracks executions, polls status and retrieves structured output. | Real health check [157](http://192.168.0.51:4440/project/HomeLab/execution/show/157) succeeded; execution tracking survived service restart. Failure reporting covered by mocks. Full post-acceptance suite: 55 tests passed. [Acceptance record](Rufus/README.md#real-acceptance-record--1-november-2026). |
| RUFUS-02 | DONE | Rufus uses only restricted Rundeck identity and approved-job policy; no infrastructure shell or arbitrary run-script endpoint. | Identity `rufus`, role `rufus-api`, health-check-only ACL. Rufus rejected an unapproved operation with 403; Rundeck independently rejected an unapproved job run with 403. Existing Rundeck administrative privileges unchanged. |
| RUFUS-03 | DONE | Rufus provisioning and application deployment validated with management separate from HP/Dell inference. | Current CT 111 (`rufus`, `192.168.0.52`), creation [150](http://192.168.0.51:4440/project/HomeLab/execution/show/150); Ansible provisioning `ok=23 failed=0`, application credential deployment `ok=8 failed=0`. Local Ollama disabled. One-year token policy managed by Ansible; token expiry 1 November 2027, superseded token revoked. |
| RUFUS-04 | DONE | Client-independent authenticated Rufus API established for health, job discovery, execution submission and monitoring. | [API contract](Rufus/README.md#api) and real acceptance test 157. Loopback only; controlled client transport and VS Code integration remain VSCODE work. |

AI2 was explicitly requested on 2 November 2026 after AI1 acceptance. Its
conversational/supervised-repair work is **IN PROGRESS**: current HP inference
reverified, [API contract](docs/ai2-api.md) drafted, and target-independent
conversation/approval persistence implemented in source. The APT-cache target, listed read-only diagnostics and isolated disposable
fixture are now approved. Workflow, six fixed operations and restricted ACL
additions are deployed through execution 183 (source `3277356`). All six automated validation groups and live permission boundaries passed. Fixture diagnostics and rejected-proposal acceptance passed; exact user approval, repair execution and independent recovery verification remain pending.

## P2 — Rufus VS Code integration: IMMEDIATE PRIORITY AFTER BASIC RUFUS WORKS

**Dependency:** basic Rufus and its API, RUFUS-01 through RUFUS-04. This is the next
product deliverable after basic Rufus, before OpenBao.

| ID | Status | Work and completion criteria | Evidence / dependency |
|---|---|---|---|
| VSCODE-01 | TODO | Build a thin VS Code chat extension/panel, similar in concept to the Codex chat tab, communicating through the Rufus API. | User requirement. No extension implementation is present in the inspected repository. |
| VSCODE-02 | TODO | Support persistent chat, streamed progress/results, useful current repository/file context, approved Rundeck operations, and deployment/status/log viewing. | User requirement; depends on VSCODE-01 and the shared Rufus API. |
| VSCODE-03 | TODO | Provide explicit approval/rejection for sensitive operations and carry the decision through the Rufus/Rundeck workflow. Keep execution and authorisation in the backend rather than making the panel an unrestricted infrastructure client. | User requirement; depends on RUFUS-02 and VSCODE-01. |

## GitHub/Rundeck security — separate planned track

The instruction to leave the current Git setup working remains in effect during
this documentation task. The target state below is planned, not already verified.

| ID | Status | Work and completion criteria | Evidence / dependency |
|---|---|---|---|
| GITHUB-01 | TODO | Verify repository visibility and make `emmjam/homelab-server-builds` private if not already private. | User requirement; visibility cannot be established from the local Git checkout alone. |
| GITHUB-02 | TODO | Configure the Rundeck account's Git fetch/pull with a dedicated least-privilege GitHub token, then verify GitHub records that token as used. Never put it in Git, scripts or shell history. | User requirement. [Checkout job](Rundeck/jobs/HomeLab%20-%20Update%20GitHub%20Checkout-310dfa4f-e27f-4945-be6a-7380ef75e586.yaml) already references a GitHub read-token Key Storage entry, and [the updater](Rundeck/scripts/update-github-checkout.sh) supports it. That does not prove token scope, ownership, actual use or GitHub's usage record. |
| GITHUB-03 | TODO | Verify existing Git refresh/update jobs continue working after the repository becomes private, using the intended Rundeck credential. | Depends on GITHUB-01 and GITHUB-02. Preserve existing SSH keys unless a separately authorised change requires otherwise. |

## P3 — OpenBao: AFTER RUFUS AND THE RUFUS VS CODE WORK

**Dependency:** working basic Rufus and completed VSCODE-01 through VSCODE-03.
These requirements are queued here; no OpenBao deployment is implied.

| ID | Status | Work and completion criteria | Evidence / dependency |
|---|---|---|---|
| BAO-01 | TODO | Deploy OpenBao natively in a lightweight Debian LXC on TNAS and manage it with Ansible. | User requirement; use the validated LXC foundation. |
| BAO-02 | TODO | Make OpenBao the central secrets service for Rufus, Rundeck, Ansible and future applications. Give applications separate restricted identities and policies. | User requirement; depends on BAO-01. |
| BAO-03 | TODO | Create a version-controlled Bash management CLI supporting secret and policy add/change/delete. Keep secret values out of the CLI source and Git history. | User requirement; depends on BAO-01 and BAO-02. |
| BAO-04 | TODO | Make successful secret/policy modifications trigger a Raft snapshot backup to the existing TNAS Samba backup share and verify that backup. Make backup failures visible. | User requirement; depends on BAO-03. The exact existing share path/access details must be established at implementation time; they are not specified in this repository. |
| BAO-05 | TODO | Add a daily safety backup, agreed retention and a verified recovery procedure. | User requirement; depends on BAO-04. Do not mark recovery complete solely because a snapshot file exists. |
| BAO-06 | TODO | Once OpenBao and recovery are proven, migrate appropriate secrets out of Rundeck Key Storage and the documented temporary local/file-based store. | User requirement and [temporary secrets context](PROJECT_CONTEXT.md). Depends on BAO-02 through BAO-05; preserve working integrations during migration. |

## Rundeck operations and privilege boundaries

| ID | Status | Work and completion criteria | Evidence / dependency |
|---|---|---|---|
| RD-01 | DONE | Store the existing Rundeck job and pipeline definitions in GitHub rather than only in the UI, preserving UUIDs and automatically synchronising managed definitions from Git. | [Jobs](Rundeck/jobs/), [pipelines](Rundeck/pipelines/), [refresh script](Rundeck/scripts/update-github-checkout.sh); commit `d86c649`. The inspected tree contains 10 reusable jobs and 3 pipelines. |
| RD-02 | TODO | Investigate executions that show status without useful visible step output/logs; ensure useful output and correct exit-status propagation throughout the affected workflows. | Explicit outstanding work in project context section 8. Logging statements in some scripts do not establish that the UI/output problem is resolved everywhere. |
| RD-03 | TODO | Create one Git-managed wrapper for the approved privileged commands currently requiring separate sudoers entries. Have Rundeck deploy/update the wrapper whenever its Git version changes, and use a **single narrowly scoped NOPASSWD sudoers rule** for that wrapper. Incorporate the documented fixed temporary execution path, safe ownership/permissions, actual exit-status capture and reliable cleanup on success, failure and interruption. | Explicit user requirement for a single `visudo` rule and Git/Rundeck-managed wrapper; [outstanding privilege mechanism](Rundeck/README.md#tnas-execution-and-privilege-boundary). Project context proposes `/opt/homelab-server-builds/scripts/rundeck-task.sh` for temporary execution. Existing per-script permissions and the LXC sudoers file do not complete this work. |
| RD-04 | DONE | Provide controlled Wake-on-LAN and sleep jobs for the HP `ai-agent` and Dell `ai-worker`, suitable for invocation through Rundeck. | [Power script](Rundeck/scripts/power-ai-host.sh), job UUID `7d9a3328-c8df-4e31-bbf6-49a6d9ce5a11`; commit `b3ca1ef`. Project context section 8 records successful wake/sleep tests on both hosts and API invocation from AI-mgmnt. |
| RD-05 | TODO | Verify the HP/Dell power-management settings and wake behaviour persist across host reboots. | Project context section 8 explicitly records that persistence has not been verified. Do not recreate RD-04 as new work. |
| RD-06 | TODO | Review the Debian guest baseline's broad Rundeck sudo grant as a distinct least-privilege change. | [debian-baseline.sh](scripts/debian-baseline.sh) still writes `rundeck ALL=(ALL) NOPASSWD: ALL`; the need for review is explicit in `Rundeck/README.md`. Separate from RD-03 on TNAS. |
| RD-07 | TODO | Reconcile the documented temporary SSH-key cleanup with the actual files still in use before removing anything. Preserve the working Rundeck SSH identity. | Project context section 8 records temporary setup keys and deferred cleanup; their current existence/use is not established by that old note. |

Rufus consumption of RD-04 belongs to RUFUS-01. Mac power-management support belongs
to MAC-02 below; the existing allowlist covers only the HP and Dell.

## Debian provisioning and DNS

| ID | Status | Work and completion criteria | Evidence / dependency |
|---|---|---|---|
| DNS-01 | DONE | Put the hostname-registration workaround in provisioning rather than adding the registration checker to the Debian VM baseline/template. | [provision-vm.sh](Rundeck/scripts/provision-vm.sh) installs it after cloning and Cloud-Init. [debian-baseline.sh](scripts/debian-baseline.sh) does not install that checker. Keep this placement rule during future changes; see DEBIAN-01 for an older template-validation inconsistency. |
| DNS-02 | DONE | At provisioning boot, compare the final hostname/current DHCP IPv4 with Pi-hole DNS at `192.168.0.2`; renew DHCP if missing/wrong, retry and log the outcome. | Provisioner embeds the checker, installs an `@reboot` cron entry, waits for networking, runs `dig`/`dhclient`, logs results and reboots the guest. Commits `12571a0`, `d65c5a6`, `71e3cf8`, `e5df1f3`. Current behaviour is a one-off provisioning boot check; the checker is removed afterwards. |
| DNS-03 | TODO | Investigate eliminating the DHCP renewal/cron workaround by cleaning inherited leases, generated network configuration and cached identity, then supplying each clone’s final hostname and networking before first boot. VM Cloud-Init and LXC Proxmox configuration must provide DHCP, Pi-hole DNS and lan search domain. Test fresh VM and LXC clones with renewal disabled and prove the first DHCP request/DNS registration uses the final hostname before removing the workaround. | Explicit user request on 1 November 2026. Existing VM cleanup uses cloud-init clean --logs --machine-id; assess network-config cleanup per [Cloud-Init 25.2 CLI documentation](https://docs.cloud-init.io/en/25.2/reference/cli.html). Removing files alone does not prove hostname/network startup ordering. Investigation only; no workaround removal authorised by this item. |
| DEBIAN-01 | TODO | Finish the documented verification/consolidation of Debian provisioning and template scripts. Reconcile the rebuild validator's older `homelab-dhcp-renew-once`/service checks with the generic-template rule and current baseline, without moving the provisioning checker into the template. | Project context section 12 lists this as high priority. [Rebuild validator](Rundeck/scripts/rebuild-debian-template.sh) still requires that one-time renewal service, while the current baseline does not create it. |
| DEBIAN-02 | TODO | Reconcile stale implementation-status documentation with the actual tracked files and this backlog. | Root `README.md` and Ansible placeholder READMEs still claim no playbooks/roles exist; older Rundeck/context text also predates the LXC and secrets-reader work. This file is authoritative meanwhile. |

## Mac workers

| ID | Status | Work and completion criteria | Evidence / dependency |
|---|---|---|---|
| MAC-01 | TODO | Plan and implement OS upgrades on both Mac Pros, checking their actual specifications and installed OS before choosing the upgrade path. | User requirement; project context section 9 records two available Mac Pros and historical Ubuntu 20 installations, but no verified upgrade. |
| MAC-02 | TODO | Integrate Mac Wake-on-LAN and availability management with Rufus/Rundeck using controlled operations. | User requirement; depends on MAC-01 and the Rufus integration. Existing HP/Dell power-job completion is not evidence of Mac support. |

## Queued infrastructure roadmap from existing documentation

These items are explicitly recorded in `PROJECT_CONTEXT.md`; they are not inferred
feature requests. No relative implementation order within this queue has been agreed.

| ID | Status | Documented work | Source / constraint |
|---|---|---|---|
| AI-01 | IN PROGRESS | Complete the AI interface, agent and worker deployment; develop the hybrid online/local model arrangement and distributed workload coordination. | Project context sections 2, 9, 10 and 12. Existing [Ollama installer](scripts/install_ai.sh) and power job provide parts, not the complete system. AI1 DONE, 2 November: retained Ollama 0.40.13/qwen3:4b adopted through Ansible. [Acceptance 171](http://192.168.0.51:4440/project/HomeLab/execution/show/171) passed real Rufus inference, controller denial and bounded errors; second run changed=0 on every host. Dedicated firewall allows only verified Rufus IPv4 remotely. [Acceptance record](docs/ai-inference.md#real-acceptance--2-november-2026). Controlled WOL test 167/168 passed; long-sleep DHCP/DNS recovery remains under investigation. AI2/distributed coordination remain outstanding. HP is primary inference, Dell is a worker, TNAS is management; only one AI model/AI VM should run at a time per compute machine. |
| AI-02 | TODO | Integrate Rufus with infrastructure monitoring and automation, and expand distributed AI computing across available machines. | Project context sections 10 and 12. Coordinate with RUFUS-01 and MAC-02 rather than duplicating them. |
| NET-01 | TODO | Improve Pi-hole DNS with Unbound, DNSSEC and encrypted DNS. | Project context sections 4 and 12. |
| NET-02 | TODO | Improve DHCP management usability/interface. | Project context sections 4 and 12; distinct from completed client hostname registration. |
| PXE-01 | TODO | Implement the planned PXE infrastructure: Pi-hole DHCP options and on-demand iVentoy; assess PXE Boot0r as the documented alternative if needed. | Project context sections 11 and 12. Keep PXE independent of the working cloud-init VM pipeline; preserve `/tank/data/shared/ISO` as the actual ISO location. |
| TNAS-01 | TODO | Improve temperature-guard logging to include the three highest CPU-consuming processes in high-temperature logs. | Project context sections 3 and 12; the temperature guard/timer already exists according to that context. |
| GATEWAY-01 | TODO | Implement a Debian gateway and investigate standby gateway HA/failover. | Project context sections 12 and 13. Keep the primary gateway independent of optional VPN services, with Vodafone connectivity as fallback. |
| VPN-01 | TODO | Implement the separately planned NordVPN/Squid proxy VM for selected traffic. | Project context sections 12 and 13. VPN failure must not cause a general network outage. |
| MEDIA-01 | TODO | Finalise and deploy the separate Bobarr/Plex media-library project and authenticated HTTPS media access through `emmjam.linkpc.net`, using the proposed Debian VM/Nginx/Certbot arrangement. | Project context sections 2 and 4. Exact deployment details are undecided. This is separate from Rufus; no public exposure without authentication and HTTPS. |

## Plex networking

| ID | Status | Work and completion criteria | Evidence / dependency |
|---|---|---|---|
| MEDIA-02 | TODO | Give Plex its own LAN IP address rather than sharing TNAS's address. Inspect the current network configuration, assign a dedicated address and verify Plex access and playback. | Explicit user request on 1 November 2026; current addressing has not been verified for this backlog update. |
| MEDIA-03 | TODO | Automate backup of Plex settings and its database, then provide an Ansible rebuild/restore process that reapplies them to a replacement container. Verify a restore before relying on the backup. | Explicit user request on 1 November 2026. Backup location, retention and consistent database backup method remain to be agreed. |

## APT cache

| ID | Status | Work and completion criteria | Evidence / dependency |
|---|---|---|---|
| CACHE-01 | TODO | Migrate Apt-Cache from a VM to an LXC container with its cache storage backed by TNAS. Assess Samba/SMB and select the storage protocol and mount arrangement before implementation; verify caching, expiration and disk monitoring after migration. | Explicit user request on 1 November 2026. Samba is a proposal, not an agreed choice. Preserve the working cache until the replacement is verified. |
| CACHE-02 | TODO | Standardise APT cache settings across templates, provisioning scripts, Ansible playbooks and existing clients. Identify inconsistencies, define one managed configuration and verify consistent HTTP proxy, HTTPS DIRECT and cache-server bootstrap behaviour. | Explicit user request on 1 November 2026; review and implementation remain outstanding. |

## Testing efficiency

| ID | Status | Work and completion criteria | Evidence / dependency |
|---|---|---|---|
| TEST-01 | TODO | Review whether existing tests can be amalgamated into single scripts returning clear exit/status codes and concise output, reducing agent token use while retaining useful failure diagnostics. | Explicit user request on 1 November 2026. Review only; no test consolidation has been implemented. |

## Maintaining this backlog

Update the existing ID when work starts, becomes blocked or completes. Add the
completion commit and relevant test/execution evidence, or name the unresolved
prerequisite. If an older document calls a completed item planned, preserve the
supported DONE status here instead of duplicating the task. If new inspection
contradicts a status, record the specific evidence and revise it.
