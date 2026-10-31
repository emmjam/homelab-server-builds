# Shared Scripts

This directory contains the flat set of shared scripts and configuration files:

- `debian-baseline.sh` — Debian guest baseline configuration.
- `PXE_debian13_preseed.cfg` — Debian network-install preseed configuration.
- `AI_lxc.sh` — existing TNAS LXC provisioning procedure.
- `install_ai.sh` — Ollama and model installation on an existing Debian VM.
- `rundeck_build.sh` — Rundeck service installation on a dedicated Debian VM.

Rundeck-specific wrappers and the Proxmox scripts deployed to TNAS live in `Rundeck/scripts/`.
