# Homelab Server Builds

GitHub is the source of truth for homelab automation definitions and supporting scripts. Rundeck runs approved workflows and deploys the Proxmox scripts to TNAS at `192.168.0.101`.

## Repository layout

- `Rundeck/jobs/` — versioned YAML definitions for reusable Rundeck jobs.
- `Rundeck/pipelines/` — versioned YAML definitions for complete workflows.
- `Rundeck/scripts/` — Rundeck helpers and Proxmox scripts deployed to TNAS; LXC execution scripts live in `Rundeck/scripts/`.
- `scripts/` — flat collection of shared Debian, PXE, LXC, system, and service scripts.
- `Ansible/` — managed inventories, roles and deployment/acceptance playbooks.
- `docs/` — operational documentation.

See [Rundeck/README.md](Rundeck/README.md) for job synchronization and Rufus integration. See [docs/debian-template.md](docs/debian-template.md) for template build and VM provisioning details.

## Rufus

See [Rufus/README.md](Rufus/README.md) for the application development entry point,
AI1–AI3 technical specifications and completion records.

## Debian 13 baseline

The guest baseline is [scripts/debian-baseline.sh](scripts/debian-baseline.sh). It configures QEMU Guest Agent, SSH hardening, `vi` as the system default editor, Fail2ban, unattended upgrades, and validates services. The template pipeline downloads and runs it on a candidate VM, then removes the temporary copy before promotion.

Run it manually as root inside a Debian 13 VM only after inspecting it and confirming authorised key-based access:

```bash
sudo bash scripts/debian-baseline.sh
```

## Physical host Wake-on-LAN

The HP ai-agent and Dell ai-worker support suspend-to-RAM and magic-packet WOL. Their current NIC settings report `Wake-on: g`, and deep suspend-to-RAM is selected. Enable WOL/PCIe wake in firmware and disable ErP/deep power saving where applicable. The controlled Rundeck job uses fixed host MACs for wake and SSH for sleep; the AI-mgmnt VM can invoke it.

## Security and change process

- Keep passwords, private SSH keys, tokens, and other credentials out of Git. Rundeck secrets belong in Key Storage.
- Review job YAML and scripts before importing or synchronising them into Rundeck.
- Test provisioning changes on a disposable VM before promoting a template.

## Development validation

Read [AGENTS.md](AGENTS.md) for permanent development directives. Run
`python3 scripts/validate.py` for a compact repository validation summary.
See [docs/validation.md](docs/validation.md) for diagnostics and pipeline scope.
