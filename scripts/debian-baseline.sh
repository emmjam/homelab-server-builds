#!/usr/bin/env bash
set -Eeuo pipefail

LOG_TAG="homelab-debian-baseline"

log() {
    printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$*"
    logger -t "$LOG_TAG" -- "$*" 2>/dev/null || true
}

fail() {
    log "ERROR: $*"
    exit 1
}

[[ $EUID -eq 0 ]] || fail "Run this script as root."
[[ -r /etc/os-release ]] || fail "Cannot identify operating system."
. /etc/os-release

[[ "${ID:-}" == "debian" ]] || fail "Expected Debian; found ${ID:-unknown}."
[[ "${VERSION_ID:-}" == "13" ]] || fail "Expected Debian 13; found ${VERSION_ID:-unknown}."

export DEBIAN_FRONTEND=noninteractive

log "Updating package lists."
apt-get update

log "Installing baseline packages."
apt-get install -y \
    qemu-guest-agent \
    fail2ban \
    unattended-upgrades \
    openssh-server

log "Configuring SSH hardening."
install -d -m 0755 /etc/ssh/sshd_config.d

cat > /etc/ssh/sshd_config.d/00-homelab-hardening.conf <<'SSH'
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
SSH

/usr/sbin/sshd -t || fail "SSH configuration validation failed."

log "Enabling and starting SSH."
systemctl enable --now ssh
systemctl reload ssh

log "Configuring fail2ban SSH protection."
install -d -m 0755 /etc/fail2ban/jail.d

cat > /etc/fail2ban/jail.d/sshd.local <<'FAIL2BAN'
[sshd]
enabled = true
FAIL2BAN

systemctl enable --now fail2ban
systemctl restart fail2ban

log "Configuring unattended security updates."
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT

systemctl enable --now apt-daily.timer apt-daily-upgrade.timer

log "Enabling QEMU Guest Agent."
systemctl enable --now qemu-guest-agent

log "Validating baseline."
systemctl is-active --quiet ssh ||
    fail "SSH service is not active."

systemctl is-active --quiet fail2ban ||
    fail "Fail2ban is not active."

fail2ban-client status sshd ||
    fail "Fail2ban SSH jail is unavailable."

systemctl is-active --quiet qemu-guest-agent ||
    fail "QEMU Guest Agent is not active."

systemctl is-enabled --quiet apt-daily.timer ||
    fail "APT update timer is not enabled."

systemctl is-enabled --quiet apt-daily-upgrade.timer ||
    fail "APT upgrade timer is not enabled."

SSH_EFFECTIVE="$(sshd -T)"
grep -qx 'permitrootlogin no' <<< "$SSH_EFFECTIVE" ||
    fail "Root SSH login is not disabled."
grep -qx 'pubkeyauthentication yes' <<< "$SSH_EFFECTIVE" ||
    fail "SSH public-key authentication is not enabled."
grep -qx 'passwordauthentication no' <<< "$SSH_EFFECTIVE" ||
    fail "SSH password authentication is not disabled."
grep -qx 'kbdinteractiveauthentication no' <<< "$SSH_EFFECTIVE" ||
    fail "SSH keyboard-interactive authentication is not disabled."

log "PASS: Debian baseline installed and validated."
