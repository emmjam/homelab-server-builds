# Homelab Server Builds

Version-controlled build definitions for reusable Debian servers in the homelab.

## Debian 13 baseline

Script: `scripts/debian-baseline.sh`

The baseline configures:

- QEMU Guest Agent
- OpenSSH with public-key authentication and password authentication disabled
- Root SSH login disabled
- Fail2ban with the SSH jail enabled
- APT automatic package-list updates and unattended upgrades
- Service and effective SSH configuration validation

The script is designed to run as root inside a Debian 13 VM. It stops on errors and exits unsuccessfully if a required validation fails.

## Run

Copy the script to the target Debian 13 VM, inspect it, then execute it as root:

    sudo bash debian-baseline.sh

Run from a console or an existing privileged session. Confirm that key-based SSH access works for an authorised non-root account before relying on the hardened SSH configuration.

## Validation

A successful run ends with:

`PASS: Debian baseline installed and validated.`

This confirms the checks implemented by the script passed; it does not replace testing a fresh VM clone.

## Security

- Never commit passwords, private SSH keys, tokens, or other secrets.
- Keep access to this repository restricted.
- Test changes on a disposable VM clone before promoting a build to a reusable template.

## Planned workflow

1. Maintain build definitions in Git.
2. Apply the baseline to the Debian 13 Cloud-Init build candidate.
3. Verify a fresh clone behaves correctly.
4. Promote the verified VM to a Proxmox template.
5. Use Rundeck for controlled orchestration when that component is ready.
