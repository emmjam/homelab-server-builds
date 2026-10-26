# Debian 13 Golden Template

## Overview

The Debian 13 (Trixie) Golden Template serves as the hardened, standardized base image for provisioning Linux virtual machines across the homelab infrastructure on Proxmox VE.

The build process is automated by `scripts/rebuild-debian-template.sh`, which enforces strict safety policies, executes the baseline hardening script (`scripts/debian-baseline.sh`), verifies Cloud-Init DHCP and SSH services, and atomically promotes the tested candidate while retaining a rollback backup.

---

## Template Specifications

- **Template VM ID**: `9000`
- **Template Name**: `debian-13-template`
- **Candidate VM ID**: `9998` (`debian-13-candidate`)
- **Rollback Backup VM ID**: `9999` (`debian-13-template-backup`)
- **Base OS**: Debian 13 Generic AMD64 Cloud Image
- **Storage**: `local-zfs`
- **Network**: `vmbr0`, Cloud-Init DHCP IPv4
- **Cloud-Init User**: `ian` (SSH key authentication only)
- **APT Cache Proxy**: `http://192.168.0.101:3142` (`apt-cacher-ng` on TNAS)
- **Locale**: `en_GB.UTF-8`

---

## Baseline Hardening Configuration

The reusable baseline script (`scripts/debian-baseline.sh`) configures and validates:

1. **APT Cache Proxy**:
   - Injects `/etc/apt/apt.conf.d/02proxy` pointing to `http://192.168.0.101:3142`.
   - Rewrites Debian mirror lists to use HTTP via the local proxy cache.

2. **Locale & Packages**:
   - Generates and enforces `en_GB.UTF-8` system-wide.
   - Installs `qemu-guest-agent`, `fail2ban`, `unattended-upgrades`, and `openssh-server`.

3. **SSH Security Hardening** (`/etc/ssh/sshd_config.d/00-homelab-hardening.conf`):
   - `PermitRootLogin no`: Direct root SSH access disabled.
   - `PubkeyAuthentication yes`: Public-key authentication enforced.
   - `PasswordAuthentication no`: Password authentication disabled.
   - `KbdInteractiveAuthentication no`: Keyboard-interactive authentication disabled.
   - Validated via runtime check with `sshd -T`.

4. **Fail2ban Protection**:
   - Configures `/etc/fail2ban/jail.d/sshd.local` to protect the SSH service.
   - Validates that the `sshd` jail starts and reports healthy status.

5. **Automated Security Updates**:
   - Enables `apt-daily.timer` and `apt-daily-upgrade.timer`.
   - Configures `/etc/apt/apt.conf.d/20auto-upgrades` for automated security patching.

6. **Environment & PATH**:
   - Configures `/etc/profile.d/00-sbin-path.sh` to include `/usr/sbin` in standard user shell sessions.

7. **QEMU Guest Agent**:
   - Manages the agent service cleanly without disrupting active guest-exec execution sessions.

---

## Automated Rebuild & Promotion Process

The build automation is managed by `scripts/rebuild-debian-template.sh` running as root on the Proxmox host.

### Build Workflow

```
[Template 9000]
       │ (Full Clone)
       ▼
[Candidate 9998] ──> Boot ──> QGA Ready ──> Cloud-Init Done ──> DHCP IPv4 Assigned
       │
       ├──> Verify SSH Keys & Port 22 Reachable
       ├──> Fetch & Execute debian-baseline.sh (Monitored via Guest PID)
       ├──> Run Post-Baseline System & Hardening Validation
       ├──> Clean Cloud-Init State (cloud-init clean --logs --machine-id)
       └──> Power Off Candidate
               │
   ┌───────────┴────────────────────────────────────────┐
   │ (All tests pass: Promotion Phase)                  │
   ▼                                                    ▼
[Rollback Backup 9999]                          [Template 9000]
(Refreshed from current 9000)                  (Replaced from tested 9998)
```

### Safety and Promotion Policy

1. **Pre-flight Invariants**:
   - Template `9000` must exist and be marked as a Proxmox template (`template: 1`).
   - Candidate ID `9998` must not already exist.
   - Existing rollback template `9999` is recognized and safely refreshed during promotion.

2. **Pre-Promotion Isolation**:
   - During candidate building and testing, template `9000` and rollback backup `9999` are untouched.
   - If any step fails before promotion, candidate `9998` is automatically stopped and destroyed (`--purge 1`). Template `9000` remains unmodified.

3. **Atomic Promotion**:
   - Once all validation tests pass and candidate `9998` is stopped cleanly:
     1. Any prior rollback template at `9999` is removed.
     2. Current template `9000` is cloned to `9999` (`debian-13-template-backup`) and converted to a template.
     3. Old template `9000` is destroyed.
     4. Tested candidate `9998` is cloned to `9000` (`debian-13-template`) and converted to a template.
     5. Temporary candidate `9998` is purged.

---

## Validation Results

The automated rebuild pipeline performs comprehensive validation checks across each phase:

### 1. Cloud-Init & Network Validation
- **Cloud-Init Completion**: Verified via `cloud-init status --wait`, confirming completion (`status: done`).
- **DHCP IPv4 Lease**: Confirmed candidate dynamically receives a non-loopback IPv4 lease via `qm guest cmd <vmid> network-get-interfaces`.
- **Authorized Keys**: Confirms Cloud-Init user `ian` exists and `/home/ian/.ssh/authorized_keys` is non-empty.
- **Network Port Accessibility**: Verifies TCP port 22 is open and reachable on the assigned DHCP IP.

### 2. Baseline Execution & Process Monitoring
- **Guest PID Tracking**: Baseline script launches asynchronously inside the guest, records its PID to `/root/baseline.pid`, and records its exit code to `/root/baseline.status`.
- **Process Polling**: Host monitors the guest PID lifecycle via `kill -0 <PID>`, capturing completion immediately upon exit without relying on brittle QMP process-table polling.
- **Exit Status Verification**: Exit code is verified as `0`. On non-zero exit or timeout, `/var/log/debian-baseline.log` is automatically dumped to the host output.

### 3. Service & OS Verification
- **OS Release**: Confirmed `ID=debian` and `VERSION_ID=13`.
- **SSH Daemon Configuration**: Verified syntax with `sshd -t` and effective runtime options via `sshd -T`:
  - `permitrootlogin no`
  - `pubkeyauthentication yes`
  - `passwordauthentication no`
  - `kbdinteractiveauthentication no`
- **Active Systemd Units**:
  - `ssh.service` (active and enabled)
  - `fail2ban.service` (active with operational `sshd` jail)
  - `qemu-guest-agent.service` (active)
  - `apt-daily.timer` and `apt-daily-upgrade.timer` (active and enabled)
- **Artifact Cleanup**: Verified that temporary baseline scripts, status files, and PID records in `/root` are removed.
- **Template Preparation**: Verified Cloud-Init state reset (`cloud-init clean --logs --machine-id`).

---

## Provisioning Virtual Machines

New virtual machines are provisioned using `scripts/provision-vm.sh`:

```bash
./scripts/provision-vm.sh <vmid> <vm-name>
```

The script:
1. Validates input syntax and ensures `<vmid>` and `<vm-name>` are not already in use.
2. Verifies template `9999` exists and is marked as a template.
3. Performs a full clone from `9999` to `<vmid>`, inheriting the template's preconfigured Cloud-Init DHCP and SSH configuration.
4. Boots the new virtual machine and reports its status and acquired DHCP IPv4 address.
5. Employs a cleanup trap to safely destroy any partial VM if an error occurs during provisioning, leaving the source template untouched.
