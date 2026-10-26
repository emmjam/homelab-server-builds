#!/usr/bin/env bash
set -Eeuo pipefail

LOG_TAG="homelab-debian-baseline"
REBOOT_REQUIRED=0

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

# Configure Debian repositories to use the TNAS apt-cacher-ng proxy.
if [[ -f /etc/apt/mirrors/debian.list ]]; then
    sed -i 's|https://deb.debian.org|http://deb.debian.org|g' \
        /etc/apt/mirrors/debian.list
fi

if [[ -f /etc/apt/mirrors/debian-security.list ]]; then
    sed -i 's|https://deb.debian.org|http://deb.debian.org|g' \
        /etc/apt/mirrors/debian-security.list
fi

cat > /etc/apt/apt.conf.d/02proxy <<'EOF'
Acquire::http::Proxy "http://192.168.0.101:3142";
EOF

cat > /etc/apt/apt.conf.d/03https-direct <<'EOF'
Acquire::https::Proxy "DIRECT";
EOF

log "Configuring a consistent UTF-8 locale."
apt-get update
apt-get install -y locales
sed -i 's/^# *en_GB.UTF-8 UTF-8/en_GB.UTF-8 UTF-8/' /etc/locale.gen
locale-gen en_GB.UTF-8
update-locale LANG=en_GB.UTF-8

log "Updating package lists."
apt-get update

log "Installing baseline packages."
apt-get install -y \
    qemu-guest-agent \
    fail2ban \
    unattended-upgrades \
    openssh-server

# Ensure the intended Cloud-Init account exists before hardening SSH.
SSH_USER="${HOMELAB_SSH_USER:-ian}"
id "$SSH_USER" >/dev/null 2>&1 ||
    fail "Expected SSH user '$SSH_USER' does not exist."

SSH_HOME="$(getent passwd "$SSH_USER" | cut -d: -f6)"
[[ -n "$SSH_HOME" && -d "$SSH_HOME" ]] ||
    fail "Home directory for '$SSH_USER' is missing."

[[ -s "$SSH_HOME/.ssh/authorized_keys" ]] ||
    fail "No authorized SSH public key found for '$SSH_USER'; refusing SSH hardening."

log "Configuring SSH hardening."
install -d -m 0755 /etc/ssh/sshd_config.d

cat > /etc/ssh/sshd_config.d/00-homelab-hardening.conf <<'SSH'
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
SSH

# Add Rundeck user & SSH key
useradd --create-home --shell /bin/bash rundeck
install -d -o rundeck -g rundeck -m 700 /home/rundeck/.ssh
install -o rundeck -g rundeck -m 600 \
    /tmp/rundeck.pub /home/rundeck/.ssh/authorized_keys
rm /tmp/rundeck.pub
printf 'rundeck ALL=(ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/rundeck
chmod 0440 /etc/sudoers.d/rundeck
visudo -cf /etc/sudoers.d/rundeck

/usr/sbin/sshd -t || fail "SSH configuration validation failed."

SSH_EFFECTIVE="$(sshd -T)"
grep -qx 'permitrootlogin no' <<< "$SSH_EFFECTIVE" ||
    fail "Root SSH login is not disabled."
grep -qx 'pubkeyauthentication yes' <<< "$SSH_EFFECTIVE" ||
    fail "SSH public-key authentication is not enabled."
grep -qx 'passwordauthentication no' <<< "$SSH_EFFECTIVE" ||
    fail "SSH password authentication is not disabled."
grep -qx 'kbdinteractiveauthentication no' <<< "$SSH_EFFECTIVE" ||
    fail "SSH keyboard-interactive authentication is not disabled."

log "Enabling and starting SSH."
systemctl enable --now ssh
systemctl reload ssh

log "Configuring fail2ban SSH protection."
install -d -m 0755 /etc/fail2ban/jail.d

cat > /etc/fail2ban/jail.d/sshd.local <<'FAIL2BAN'
[sshd]
enabled = true
FAIL2BAN

fail2ban-client -t || fail "Fail2ban configuration validation failed."
systemctl enable --now fail2ban
systemctl restart fail2ban

FAIL2BAN_READY=0
for attempt in $(seq 1 10); do
    if fail2ban-client status sshd >/dev/null 2>&1; then
        FAIL2BAN_READY=1
        break
    fi
    sleep 1
done

[[ "$FAIL2BAN_READY" -eq 1 ]] ||
    fail "Fail2ban SSH jail did not become available within 10 seconds."

fail2ban-client status sshd

log "Configuring unattended security updates."
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT

systemctl enable --now apt-daily.timer apt-daily-upgrade.timer

grep -q 'APT::Periodic::Update-Package-Lists "1";' /etc/apt/apt.conf.d/20auto-upgrades ||
    fail "Automatic package-list updates are not configured."
grep -q 'APT::Periodic::Unattended-Upgrade "1";' /etc/apt/apt.conf.d/20auto-upgrades ||
    fail "Automatic unattended upgrades are not configured."

log "Enabling QEMU Guest Agent."
systemctl enable qemu-guest-agent 2>/dev/null || true

if [[ -e /dev/virtio-ports/org.qemu.guest_agent.0 ]]; then
    if ! systemctl is-active --quiet qemu-guest-agent; then
        systemctl start qemu-guest-agent
    fi
    if ! systemctl is-active --quiet qemu-guest-agent; then
        systemctl --no-pager --full status qemu-guest-agent || true
        fail "QEMU Guest Agent device exists but its service failed."
    fi
else
    REBOOT_REQUIRED=1
    log "NOTICE: QEMU Guest Agent device is not present yet."
    log "NOTICE: A VM reboot may be required before the agent can start."
fi

log "Validating baseline services."
systemctl is-active --quiet ssh ||
    fail "SSH service is not active."
systemctl is-active --quiet fail2ban ||
    fail "Fail2ban is not active."
systemctl is-enabled --quiet apt-daily.timer ||
    fail "APT update timer is not enabled."
systemctl is-enabled --quiet apt-daily-upgrade.timer ||
    fail "APT upgrade timer is not enabled."

# Ensure administrative commands are available in user shell sessions.
cat > /etc/profile.d/00-sbin-path.sh <<'EOF'
case ":$PATH:" in
    *:/usr/sbin:*) ;;
    *) PATH="$PATH:/usr/sbin" ;;
esac
export PATH
EOF
chmod 0644 /etc/profile.d/00-sbin-path.sh

if [[ "$REBOOT_REQUIRED" -eq 1 ]]; then
    log "PASS WITH REBOOT REQUIRED: baseline configured; QEMU Guest Agent needs post-reboot validation."
else
    log "PASS: baseline installed and validated."
fi
