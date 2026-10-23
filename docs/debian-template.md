# Debian 13 Golden Template

## Template

- Proxmox VM ID: 9000
- VM name: debian-13-template
- Base image: Debian 13 Generic AMD64 Cloud image
- Storage: local-zfs
- Network: vmbr0, Cloud-Init DHCP
- Cloud-Init user: ian

## Baseline

The reusable baseline script is `scripts/debian-baseline.sh`.

It configures and validates:

- QEMU Guest Agent
- SSH public-key authentication
- SSH root login disabled
- SSH password and keyboard-interactive authentication disabled
- Fail2ban SSH jail
- Unattended security updates and APT timers
- en_GB.UTF-8 locale

## Build and validation procedure

1. Create a VM from the official Debian 13 generic Cloud image.
2. Configure Cloud-Init with the intended user, SSH public key and network settings.
3. Boot the VM and run the baseline script as root.
4. Resolve any reported failures before proceeding.
5. Clean Cloud-Init state with `cloud-init clean --logs --machine-id`.
6. Shut down the VM and convert it to a Proxmox template.
7. Clone the template to a temporary VM with a unique VM ID and name.
8. Start the clone and confirm it receives its own DHCP address.
9. Test SSH access using the configured public key.
10. Verify QEMU Guest Agent and Fail2ban are active, and confirm effective SSH settings.
11. Remove the temporary test VM after validation.

## Successful validation

The template was cloned and tested successfully:

- Clone received a distinct DHCP address.
- SSH key authentication worked.
- QEMU Guest Agent and Fail2ban were active.
- SSH root login, password authentication and keyboard-interactive authentication were disabled.

## Source of truth

GitHub stores the build script and documentation. Do not store secrets in the repository. Rundeck orchestration and further automation are future work.
