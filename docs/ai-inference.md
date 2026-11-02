# AI1: HP inference backend

Status, 2 November 2026: HP reachable after the user power cycle. Existing
Ollama/model inspected and local structured inference passed. Adoption and
Rufus-only LAN access await approval. AI2 must wait for real inference from Rufus.

## Verified inspection results

- Rundeck is reachable by hostname and has Ansible installed.
- The established HP identity is `rundeck@ai-agent`, with an existing trusted
  `ai-agent` host-key record in the controller's SSH known-hosts file.
- Earlier Pi-hole NXDOMAIN cleared after the user power cycle. The HP now
  resolves to `192.168.0.118`; existing deployment SSH access has passwordless
  administrative sudo. [WOL investigation](wol-investigation.md) records the
  successful controlled suspend/wake test and unresolved long-sleep DHCP issue.
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

## Proposed adoption, pending approval

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

The source inference client is `Rufus/inference.py` (not deployed yet). It takes
URL, exact model, connect/inference timeouts and optional bearer-secret source
from configuration. It bounds context, generation and response size, disables
streaming, does not retry requests, and returns safe error messages. Its socket
connect/read timeouts are not a strict end-to-end wall-clock deadline for a
peer deliberately sending a slow response. Structured content must still be
validated against the caller's schema before any future action proposal.

The existing runtime/model and network proposal require user approval before
live configuration. Deployment must use Git → Rundeck → Ansible. No runtime
is to be installed inside Rufus. Subsequent acceptance must prove local and
Rufus-container inference, source restrictions and an idempotent second run.

References: [Ollama authentication](https://docs.ollama.com/api/authentication),
[configuration](https://docs.ollama.com/faq),
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
