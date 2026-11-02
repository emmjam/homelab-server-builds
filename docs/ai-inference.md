# AI1: HP inference backend

Status, 2 November 2026: inspection in progress; runtime/model not selected,
installed or approved. AI2 must wait for real inference from Rufus to the HP.

## Verified inspection results

- Rundeck is reachable by hostname and has Ansible installed.
- The established HP identity is `rundeck@ai-agent`, with an existing trusted
  `ai-agent` host-key record in the controller's SSH known-hosts file.
- Pi-hole returned NXDOMAIN for `ai-agent.lan`; neither HP hostname resolved
  on the laptop or controller. Hardware, OS, capacity and HP sudo permissions
  remain unverified. No IP substitution or host-key bypass was used.
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

Next: restore/confirm HP availability and hostname resolution, run inspection,
then propose one runtime and exact model with download/memory/storage estimates,
CPU/GPU limitations and a restricted Rufus access arrangement. Obtain explicit
runtime/model approval before installation or large downloads, as required by
`AI1.md`. Driver changes and reboots also require approval. Deployment must use
Git → Rundeck → Ansible; no runtime is to be installed inside Rufus.
