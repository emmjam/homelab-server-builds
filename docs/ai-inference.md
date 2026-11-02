# AI1: HP inference backend

Status, 2 November 2026: **AI1 complete**. Existing Ollama 0.40.13 and
qwen3:4b retained under Ansible management; Rufus-only LAN firewall deployed.
Real structured inference as the unprivileged Rufus account passed, controller
access was denied and the second deployment reported zero changes. AI2 has not
been started.

## Verified inspection results

- Rundeck is reachable by hostname and has Ansible installed.
- The established HP identity is `rundeck@ai-agent`, with an existing trusted
  `ai-agent` host-key record in the controller's SSH known-hosts file.
- Earlier Pi-hole NXDOMAIN cleared after the user power cycle. The HP now
  resolves to `192.168.0.118`; existing deployment SSH access has passwordless
  administrative sudo. [WOL investigation](wol-investigation.md) records the
  successful controlled suspend/wake test and historical long-sleep DHCP issue.
  The user confirmed HP/Dell long-sleep recovery fixed on 2 November 2026.
- HP hardware: i5-6500T, four cores/threads; 7824 MiB RAM; Intel HD Graphics 530;
  root filesystem 103 GiB with 91 GiB free. Debian 13.7.
- Existing Ollama 0.40.13 is active and enabled as `ollama`, bound to
  `127.0.0.1:11434`. Existing `qwen3:4b`, Q4_K_M, 2,497,293,931 bytes,
  digest `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`.
  This contradicts the original prompt's assumption of an empty host; reuse
  the verified installation instead of reinstalling it blindly.
- A local JSON-schema request returned `{"status":"ready"}` with a 4096-token
  context, thinking disabled and a 32-token generation limit. Total elapsed
  time 14.51 seconds including load; 10 generated tokens in 1.0754 seconds.
  This tiny request is a smoke test, not a representative workload benchmark.
- Rufus resolves to `192.168.0.52`; its service is active and enabled with API
  listener `127.0.0.1:8787`. Its deployed configuration has no inference URL
  or model. The existing Rundeck deployment identity can access Rufus.
- Pi-hole lease inspection was unavailable with the laptop's existing SSH
  identity. No credentials, DNS configuration or host permissions were changed.

## Repeatable read-only inspection

On the Rundeck controller, using the existing administrative execution context:

```bash
cd /opt/homelab-server-builds
ansible-playbook -i Ansible/inventory/ai-inference.ini \
  Ansible/playbooks/ai-inference-inspect.yml
```

The inventory reuses the existing deployment key and strict host-key checking.
The playbook changes no host configuration, installs nothing and reports CPU,
RAM, storage, OS, GPU, network, existing runtime paths/packages/services and
sudo permissions together. Retain the full Ansible output locally and inspect
failures plus the final summary. Common runtime paths are evidence, not an
exhaustive search for all possible manually installed runtimes or model files.

## Approved and deployed adoption

Retain Ollama 0.40.13 and the installed `qwen3:4b` digest. No model download or
GPU-driver installation is needed. Use CPU inference, one loaded model and one
request at a time, with a 4096-token context. Budget roughly 4–6 GiB RAM under
load (estimate, not measured peak); keep several GiB free for logs and updates.
The installed model occupies 2.50 GB; runtime libraries occupy roughly 2.3 GiB.

Proposed endpoint: `http://ai-agent.lan:11434`, bound to the HP LAN IPv4.
Install a dedicated nftables rule restricting that port to Rufus's verified LAN
IPv4 and local checks before enabling the LAN listener. Preserve all unrelated
firewall rules. Access is source-IP based, with no application authentication
or transport encryption. DHCP address changes must cause validation failure
and a controlled inventory/rule update; never broaden access automatically.
No proxy, secrets service or SSH credentials in Rufus are required.

The deployed inference client is `Rufus/inference.py`. It takes
URL, exact model, connect/inference timeouts and optional bearer-secret source
from configuration. It bounds context, generation and response size, disables
streaming, does not retry requests, and returns safe error messages. Its socket
connect/read timeouts are not a strict end-to-end wall-clock deadline for a
peer deliberately sending a slow response. Structured content must still be
validated against the caller's schema before any future action proposal.

The user approved the existing runtime/model and Rufus-only firewall access. Deployment must use Git → Rundeck → Ansible. No runtime
is to be installed inside Rufus. Subsequent acceptance must prove local and
Rufus-container inference, source restrictions and an idempotent second run.

References: [Ollama authentication](https://docs.ollama.com/api/authentication),
[configuration](https://docs.ollama.com/faq),
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

## Deployment and operations

Role: `Ansible/roles/ollama_inference`. Inventory: `Ansible/inventory/ai-inference.ini`.
Deployment: `Ansible/playbooks/ai-inference.yml`; repeatable acceptance:
`Ansible/playbooks/ai-inference-validate.yml`.

The deployment gathers facts through the existing trusted `rufus.lan` inventory
entry. On 2 November, its verified egress address was `192.168.0.52`, matching
project context. No address is hard-coded in firewall defaults: each deployment
uses the verified Rufus fact as a single `/32`. A later DHCP change requires a
new controlled deployment. No runtime DNS-driven firewall updater is installed.

The role preserves the executable and model blobs. Missing/different runtime or
model state fails with a request for review; it does not silently reinstall or
pull. It pins both the observed API model digest and the exact existing manifest
checksum. Referenced blob sizes are checked offline; hashing all 2.5 GB on every
run is deliberately avoided. Service account, directory, service configuration,
startup state and firewall state are managed. Every run atomically replaces only
`inet homelab_inference`; before/after comparison reports semantic rule changes.
Other firewall tables and policies are preserved. The global nftables service
is not enabled, disabled or reconfigured.

The dedicated firewall service is enabled before opening the HP IPv4 listener;
Ollama requires and is bound to that service. Firewall service stop retains the
restrictive table. This limits all Ollama API routes by client address; it does
not provide per-route permissions inside the allowed Rufus client.

Rufus receives `/opt/rufus/app/inference.py` and separate non-secret configuration
`/opt/rufus/config/inference.json`. Its API remains loopback-only. No SSH keys,
sudo grants, Rundeck policy changes or inference runtime are added to Rufus.

Use the **HomeLab - Deploy HP Inference** Rundeck job
`0b42e662-1cce-49ec-a43e-7345db516937`. It refreshes the existing Git checkout,
syntax-checks, deploys, runs acceptance and reports a compact summary. Full logs
remain under `/var/lib/rundeck/hp-inference-*.log` on Rundeck. After the job
is synced from Git, run it twice and require zero changes on the second run.

Equivalent commands on Rundeck, using its existing administrative context:

```bash
cd /opt/homelab-server-builds
export ANSIBLE_ROLES_PATH="$PWD/Ansible/roles"
ansible-playbook -i Ansible/inventory/ai-inference.ini Ansible/playbooks/ai-inference.yml
ansible-playbook -i Ansible/inventory/ai-inference.ini Ansible/playbooks/ai-inference-validate.yml
```

On HP, service operations are `sudo systemctl start ollama`,
`sudo systemctl stop ollama`, `systemctl status ollama` and
`sudo journalctl -u ollama -n 50 --no-pager`. Firewall status:
`systemctl status homelab-inference-firewall` and
`sudo nft list table inet homelab_inference`. Rerun deployment to restore the
managed state; never remove firewall rules while the LAN listener is active.

Acceptance covers enabled/active services, exact API model digest, local
structured generation, real generation as unprivileged Rufus, safe unavailable
errors on a deliberately unused loopback port, and forbidden controller access.
A controlled reboot has not been approved or performed for AI1. Unit ordering
and enabled state alone do not prove post-reboot acceptance.

## Real acceptance — 2 November 2026

- Existing runtime/model preserved; no runtime reinstall, model download, GPU
  driver change or reboot. HP endpoint `http://ai-agent.lan:11434` currently binds
  `192.168.0.118:11434`. Allowed remote source is Rufus `192.168.0.52/32`, gathered
  through the trusted inventory host. Loopback-origin HP self-checks are allowed;
  other remote IPv4 and IPv6 traffic to TCP 11434 is dropped in the dedicated table.
- [Deployment 170](http://192.168.0.51:4440/project/HomeLab/execution/show/170)
  applied HP/Rufus configuration and passed local inference. Its acceptance stage
  failed on Ansible's unprivileged temporary-file ACL handling. Commit `38da28a`
  corrected validation to use the existing root deployment context with
  `runuser -u rufus`; Rufus received no additional permissions.
- [Deployment/acceptance 171](http://192.168.0.51:4440/project/HomeLab/execution/show/171)
  succeeded. Enabled/active service checks, local structured inference, real
  structured inference as `rufus`, bounded unavailable-backend reporting and
  forbidden controller access all passed.
- Second-run recap: HP `ok=27 changed=0 failed=0`; Rufus `ok=5 changed=0 failed=0`;
  controller `ok=1 changed=0 failed=0`; all unreachable counts zero.
- Detailed successful acceptance output remains on Rundeck in
  `/var/lib/rundeck/hp-inference-cOaKFU.log`. Routine checks are in the shared
  acceptance playbook; no individual manual success checks are required.
- Repository validation passed all six stages: 67 tests plus shell syntax.
  The main adoption implementation is commit `5859259`; validation correction
  is `38da28a`. The existing checkout/job sync was execution 169.
- Post-reboot persistence was not exercised: no AI1 reboot was approved. Services
  are enabled with firewall-before-listener ordering. Source-IP filtering is
  neither application authentication nor TLS. HP/Dell long-sleep recovery was subsequently confirmed fixed by the user on
  2 November 2026; that fix is separate from this inference deployment.
- No conversational repairs, Dell worker, VS Code extension, OpenBao or other
  backlog systems were deployed. Stop this milestone here.
