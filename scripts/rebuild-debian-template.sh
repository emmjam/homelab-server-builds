#!/bin/bash
set -Eeuo pipefail

# Rebuild the Debian 13 template safely.
# Run as root on the Proxmox host.

TEMPLATE_ID=9000
CANDIDATE_ID=9998
BACKUP_ID=9999

TEMPLATE_NAME="debian-13-template"
CANDIDATE_NAME="debian-13-candidate"
BACKUP_NAME="debian-13-template-backup"

CANDIDATE_SSH_USER="ian"

BASELINE_URL="https://raw.githubusercontent.com/emmjam/homelab-server-builds/main/scripts/debian-baseline.sh"
REPO="/opt/homelab-server-builds"
cd ${REPO} || {
    printf 'ERROR: Could not change to working directory %s\n' "$REPO" >&2
    exit 1
}
REMOTE_BASE_PWD="/home/${CANDIDATE_SSH_USER}"
BASELINE_LOCAL="${REPO}/debian-baseline.sh"
BASELINE_GUEST="${REMOTE_BASE_PWD}/debian-baseline.sh"
BASELINE_PID_FILE="${REMOTE_BASE_PWD}/baseline.pid"
BASELINE_STATUS_FILE="${REMOTE_BASE_PWD}/baseline.status"
BASELINE_LOG="/var/log/debian-baseline.log"

AGENT_WAIT_ATTEMPTS=60
GUEST_TIMEOUT=60
BASELINE_TIMEOUT=600

CANDIDATE_CREATED=0
PROMOTION_STARTED=0

RUNDECK_PUBLIC_KEY="${REPO}/rundeck.pub"


log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

fail() {
    log "ERROR: $*"
    exit 1
}

guest_exec() {
    local vmid="$1"
    shift

    local result exitcode exited
    result="$(qm guest exec "$vmid" --timeout "$GUEST_TIMEOUT" -- "$@" 2>&1)" || {
        log "Guest command invocation failed on VM ${vmid}: ${result}"
        return 1
    }

    exited="$(jq -r '.exited // empty' <<<"$result")"
    exitcode="$(jq -r '.exitcode // empty' <<<"$result")"

    if [[ "$exited" != "1" || ! "$exitcode" =~ ^[0-9]+$ ]]; then
        log "Unexpected Guest Agent response on VM ${vmid}: ${result}"
        return 1
    fi

    if (( exitcode != 0 )); then
        log "Guest command failed on VM ${vmid}, exit ${exitcode}: ${result}"
        return "$exitcode"
    fi
}

guest_read_file() {
    local vmid="$1"
    local file="$2"

    local result exitcode exited
    result="$(qm guest exec "$vmid" --timeout "$GUEST_TIMEOUT" -- /usr/bin/cat "$file" 2>&1)" || {
        return 1
    }

    exited="$(jq -r '.exited // empty' <<<"$result")"
    exitcode="$(jq -r '.exitcode // empty' <<<"$result")"

    if [[ "$exited" == "1" && "$exitcode" == "0" ]]; then
        jq -r '.["out-data"] // empty' <<<"$result"
        return 0
    fi

    return 1
}

cleanup() {
    local rc=$?
    trap - EXIT

    # Always remove the temporary host copy.
    rm -f "$BASELINE_LOCAL"

    if (( rc != 0 )); then
        log "Rebuild failed."

        if (( PROMOTION_STARTED )); then
            log "Promotion had started. Do not retry until VM IDs ${TEMPLATE_ID}, ${CANDIDATE_ID}, and ${BACKUP_ID} have been inspected."
            log "Any rollback template created at VM ${BACKUP_ID} has been retained."
        else
            log "The existing template ${TEMPLATE_ID} has not been replaced."

            if (( CANDIDATE_CREATED )) &&
               qm status "$CANDIDATE_ID" >/dev/null 2>&1; then
                qm stop "$CANDIDATE_ID" --timeout 60 >/dev/null 2>&1 || true
                qm destroy "$CANDIDATE_ID" --purge 1 >/dev/null 2>&1 || true
            fi
        fi
    fi

    exit "$rc"
}
trap cleanup EXIT

[[ $EUID -eq 0 ]] || fail "Run this script as root."

for command in qm curl jq sha256sum; do
    command -v "$command" >/dev/null 2>&1 ||
        fail "Required command not found: $command"
done

log "Downloading baseline script from GitHub over HTTPS."
curl --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 \
    "$BASELINE_URL" --output "$BASELINE_LOCAL"

[[ -s "$BASELINE_LOCAL" ]] ||
    fail "Downloaded baseline script is empty."

chmod 700 "$BASELINE_LOCAL"
bash -n "$BASELINE_LOCAL" ||
    fail "Baseline script failed shell syntax validation."

log "Baseline SHA-256: $(sha256sum "$BASELINE_LOCAL" | awk '{print $1}')"

log "Checking VM IDs."
qm config "$TEMPLATE_ID" >/dev/null ||
    fail "Template VM ${TEMPLATE_ID} does not exist."

qm config "$TEMPLATE_ID" | grep -q '^template: 1$' ||
    fail "VM ${TEMPLATE_ID} is not marked as a Proxmox template."

if qm status "$CANDIDATE_ID" >/dev/null 2>&1; then
    fail "Candidate VM ${CANDIDATE_ID} already exists. Inspect it before retrying."
fi

if qm status "$BACKUP_ID" >/dev/null 2>&1; then
    log "Existing rollback template VM ${BACKUP_ID} detected; it will be refreshed during promotion."
fi

log "Cloning template ${TEMPLATE_ID} to candidate ${CANDIDATE_ID}."
qm clone "$TEMPLATE_ID" "$CANDIDATE_ID" \
    --name "$CANDIDATE_NAME" --full 1
CANDIDATE_CREATED=1

log "Starting candidate."
qm start "$CANDIDATE_ID"

log "Waiting for QEMU Guest Agent."
AGENT_READY=0

for ((i=1; i<=AGENT_WAIT_ATTEMPTS; i++)); do
    if qm agent "$CANDIDATE_ID" ping >/dev/null 2>&1; then
        AGENT_READY=1
        break
    fi
    sleep 5
done

(( AGENT_READY == 1 )) ||
    fail "Guest Agent did not become available."

log "Waiting for Cloud-Init to complete on candidate."
guest_exec "$CANDIDATE_ID" /usr/bin/env bash -c \
    'rc=0; /usr/bin/cloud-init status --wait || rc=$?; [[ "$rc" -eq 0 || "$rc" -eq 2 ]]'

log "Verifying candidate acquired a DHCP IPv4 address."
CANDIDATE_IP=""
for ((i=1; i<=30; i++)); do
    CANDIDATE_IP="$(qm guest cmd "$CANDIDATE_ID" network-get-interfaces 2>/dev/null | jq -r '
        .[]? | select(.name != "lo") | .["ip-addresses"][]? |
        select(.["ip-address-type"] == "ipv4" and (.["ip-address"] | startswith("127.") | not)) |
        .["ip-address"]
    ' 2>/dev/null | head -n 1 || true)"
    if [[ "$CANDIDATE_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        break
    fi
    sleep 2
done

[[ "$CANDIDATE_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
    fail "Candidate VM did not acquire a valid DHCP IPv4 address."

log "Candidate acquired DHCP IPv4 address: ${CANDIDATE_IP}"

log "Verifying Cloud-Init user and SSH keys on candidate."
guest_exec "$CANDIDATE_ID" /usr/bin/env bash -lc '
set -eu
SSH_USER="${HOMELAB_SSH_USER:-ian}"
id "$SSH_USER" >/dev/null
SSH_HOME="$(getent passwd "$SSH_USER" | cut -d: -f6)"
test -d "$SSH_HOME"
test -s "$SSH_HOME/.ssh/authorized_keys"
'

log "Verifying SSH service is reachable on port 22 on ${CANDIDATE_IP}."
SSH_PORT_READY=0
for ((i=1; i<=15; i++)); do
    if timeout 3 bash -c "</dev/tcp/${CANDIDATE_IP}/22" >/dev/null 2>&1; then
        SSH_PORT_READY=1
        break
    fi
    sleep 2
done
if (( SSH_PORT_READY )); then
    log "SSH port 22 on ${CANDIDATE_IP} is reachable from host."
else
    log "NOTICE: Port 22 not directly reachable from host; verifying guest SSH listener."
    guest_exec "$CANDIDATE_ID" /usr/bin/env bash -lc '
        command -v ss >/dev/null && ss -tln | grep -q ":22 " || systemctl is-active --quiet ssh
    '
fi

log "Copying over SSH key"
KEY_BASE64="$(base64 -w0 "$RUNDECK_PUBLIC_KEY")"
qm guest exec "$CANDIDATE_ID" -- \
    bash -c "echo '$KEY_BASE64' | base64 -d > /tmp/rundeck.pub"

log "Checking guest prerequisites."
guest_exec "$CANDIDATE_ID" /usr/bin/env bash -lc \
    'command -v curl >/dev/null &&
     test -d ${REPO} &&
     test "$(id -u)" = 0'

log "Downloading baseline script inside candidate over HTTPS."
guest_exec "$CANDIDATE_ID" /usr/bin/curl \
    --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 \
    "$BASELINE_URL" --output "$BASELINE_GUEST"

log "Setting permissions and checking guest script syntax."
guest_exec "$CANDIDATE_ID" /usr/bin/chmod 700 "$BASELINE_GUEST"
guest_exec "$CANDIDATE_ID" /usr/bin/bash -n "$BASELINE_GUEST"

log "Preparing candidate for Debian baseline execution."
guest_exec "$CANDIDATE_ID" /usr/bin/rm -f "$BASELINE_PID_FILE" "$BASELINE_STATUS_FILE"

log "Launching Debian baseline in candidate VM."
guest_exec "$CANDIDATE_ID" /usr/bin/env bash -c \
    "( /usr/bin/bash \"$BASELINE_GUEST\" > \"$BASELINE_LOG\" 2>&1; echo \$? > \"$BASELINE_STATUS_FILE\" ) </dev/null >/dev/null 2>&1 & echo \$! > \"$BASELINE_PID_FILE\""

log "Getting baseline PID."
BASELINE_PID="$(guest_read_file "$CANDIDATE_ID" "$BASELINE_PID_FILE" | tr -d '\r\n[:space:]')"
[[ "$BASELINE_PID" =~ ^[0-9]+$ ]] ||
    fail "Could not retrieve valid baseline PID from candidate VM (got: '${BASELINE_PID}')."

log "Debian baseline running with PID ${BASELINE_PID} inside candidate VM."

log "Monitoring baseline process ${BASELINE_PID} until it exits."
BASELINE_ELAPSED=0
while (( BASELINE_ELAPSED < BASELINE_TIMEOUT )); do
    sleep 5
    (( BASELINE_ELAPSED += 5 ))

    # Check if process is still running
    if ! guest_exec "$CANDIDATE_ID" /usr/bin/kill -0 "$BASELINE_PID" >/dev/null 2>&1; then
        log "Baseline process ${BASELINE_PID} has finished."
        break
    fi

    if (( BASELINE_ELAPSED % 30 == 0 )); then
        log "Debian baseline (PID ${BASELINE_PID}) still running (${BASELINE_ELAPSED}s / ${BASELINE_TIMEOUT}s)..."
    fi
done

if (( BASELINE_ELAPSED >= BASELINE_TIMEOUT )); then
    log "ERROR: Baseline script timed out after ${BASELINE_TIMEOUT} seconds."
    if guest_log="$(guest_read_file "$CANDIDATE_ID" "$BASELINE_LOG" 2>/dev/null)"; then
        log "Tail of baseline log inside candidate:"
        tail -n 50 <<<"$guest_log" | while IFS= read -r line; do log "  $line"; done
    fi
    fail "Debian baseline timed out after ${BASELINE_TIMEOUT} seconds."
fi

BASELINE_EXIT_CODE="$(guest_read_file "$CANDIDATE_ID" "$BASELINE_STATUS_FILE" 2>/dev/null | tr -d '\r\n[:space:]' || true)"
if [[ "$BASELINE_EXIT_CODE" != "0" ]]; then
    log "ERROR: Debian baseline failed with exit code ${BASELINE_EXIT_CODE:-unknown}."
    if guest_log="$(guest_read_file "$CANDIDATE_ID" "$BASELINE_LOG" 2>/dev/null)"; then
        log "Tail of baseline log inside candidate:"
        tail -n 50 <<<"$guest_log" | while IFS= read -r line; do log "  $line"; done
    fi
    fail "Debian baseline failed with exit code ${BASELINE_EXIT_CODE:-unknown}."
fi

log "Debian baseline completed successfully (exit code 0) in approximately ${BASELINE_ELAPSED} seconds."

log "Removing guest copies of baseline script, PID, and status files."
guest_exec "$CANDIDATE_ID" /usr/bin/rm -f "$BASELINE_GUEST" "$BASELINE_PID_FILE" "$BASELINE_STATUS_FILE"
guest_exec "$CANDIDATE_ID" /usr/bin/test '!' -e "$BASELINE_GUEST"
guest_exec "$CANDIDATE_ID" /usr/bin/test '!' -e "$BASELINE_PID_FILE"
guest_exec "$CANDIDATE_ID" /usr/bin/test '!' -e "$BASELINE_STATUS_FILE"

log "Validating candidate OS, SSH hardening, and baseline services."
guest_exec "$CANDIDATE_ID" /usr/bin/env bash -lc '
set -eu
. /etc/os-release
test "$ID" = debian
test "${VERSION_ID%%.*}" = 13

# Validate SSH configuration
test -x /usr/sbin/sshd
/usr/sbin/sshd -t
systemctl is-enabled ssh.service >/dev/null
systemctl is-active ssh.service >/dev/null

# Validate SSH hardening settings
SSH_CONFIG="$(sshd -T)"
grep -qx "permitrootlogin no" <<< "$SSH_CONFIG"
grep -qx "pubkeyauthentication yes" <<< "$SSH_CONFIG"
grep -qx "passwordauthentication no" <<< "$SSH_CONFIG"
grep -qx "kbdinteractiveauthentication no" <<< "$SSH_CONFIG"

# Validate core baseline services
systemctl is-active --quiet fail2ban
systemctl is-active --quiet qemu-guest-agent
systemctl is-enabled --quiet apt-daily.timer
systemctl is-enabled --quiet apt-daily-upgrade.timer

# Confirm cleanup of baseline files
test ! -e ${REPO}/debian-baseline.sh
test ! -e ${REPO}/baseline.pid
test ! -e ${REPO}/baseline.status
'

log "Cleaning Cloud-Init state before template creation."
guest_exec "$CANDIDATE_ID" /usr/bin/cloud-init clean --logs --machine-id

log "Candidate passed validation. Requesting guest shutdown."
qm shutdown "$CANDIDATE_ID" --timeout 60 || {
    log "Guest shutdown request did not complete cleanly; checking VM state."
}

STOPPED=0
for ((i=1; i<=30; i++)); do
    if qm status "$CANDIDATE_ID" 2>/dev/null |
        grep -q 'status: stopped'; then
        STOPPED=1
        break
    fi
    sleep 2
done

if (( STOPPED == 0 )); then
    log "Requesting Proxmox to stop the candidate."
    qm stop "$CANDIDATE_ID" --timeout 60 ||
        fail "Could not stop candidate."
fi

log "Validation succeeded. Beginning template replacement."
PROMOTION_STARTED=1

# Remove existing rollback template from prior run before creating new rollback clone
if qm status "$BACKUP_ID" >/dev/null 2>&1; then
    log "Removing previous rollback template VM ${BACKUP_ID}."
    qm destroy "$BACKUP_ID" --purge 1 ||
        fail "Could not remove previous rollback template ${BACKUP_ID}."
fi

log "Creating rollback clone of current template ${TEMPLATE_ID} as VM ${BACKUP_ID}."
qm clone "$TEMPLATE_ID" "$BACKUP_ID" \
    --name "$BACKUP_NAME" --full 1 ||
    fail "Could not create rollback clone. Original template is untouched."

qm template "$BACKUP_ID" ||
    fail "Could not mark rollback clone as a template. Original template is untouched."

# Keep the rollback clone before removing the original.
qm destroy "$TEMPLATE_ID" --purge 1 ||
    fail "Could not remove old template. Rollback clone remains at ${BACKUP_ID}."

log "Cloning validated candidate into original template ID ${TEMPLATE_ID}."
qm clone "$CANDIDATE_ID" "$TEMPLATE_ID" \
    --name "$TEMPLATE_NAME" --full 1 ||
    fail "Could not create replacement. Rollback clone remains at ${BACKUP_ID}."

qm template "$TEMPLATE_ID" ||
    fail "Could not mark replacement as a template. Rollback clone remains at ${BACKUP_ID}."

log "Removing temporary candidate."
qm destroy "$CANDIDATE_ID" --purge 1
CANDIDATE_CREATED=0

log "SUCCESS: VM ${TEMPLATE_ID} is the rebuilt Debian 13 template."
log "Rollback template retained as VM ${BACKUP_ID}."
