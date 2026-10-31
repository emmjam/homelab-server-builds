#!/usr/bin/env bash
set -Eeuo pipefail

SSH_KEY="/var/lib/rundeck/.ssh/target_ed25519"
SSH_USER="rundeck"
SSH_CONNECT_TIMEOUT=2
WOL_BROADCAST="255.255.255.255"
WOL_PORT=9

VMNAME="${RD_OPTION_VMNAME:-}"
ACTION="${RD_OPTION_ACTION:-}"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

[[ -n "$VMNAME" ]] || fail "Select a VM name."
case "$VMNAME" in
    ai-agent)
        MAC_ADDRESS="10:62:e5:0d:17:a4"
        ;;
    ai-worker)
        MAC_ADDRESS="b0:83:fe:5b:62:5d"
        ;;
    *)
        fail "Unsupported VM name '$VMNAME'. Allowed: ai-agent, ai-worker."
        ;;
esac

case "$ACTION" in
    wake|sleep) ;;
    *) fail "Unsupported action '$ACTION'. Allowed: wake, sleep." ;;
esac

command -v ssh >/dev/null 2>&1 || fail "Required command not found: ssh"
[[ -r "$SSH_KEY" ]] || fail "Rundeck SSH key is missing or unreadable: $SSH_KEY"
SSH_TARGET="${SSH_USER}@${VMNAME}"
SSH_OPTIONS=(
    -i "$SSH_KEY"
    -o BatchMode=yes
    -o ConnectTimeout="$SSH_CONNECT_TIMEOUT"
    -o ConnectionAttempts=1
    -o StrictHostKeyChecking=no
    -o UserKnownHostsFile=/dev/null
    -o GlobalKnownHostsFile=/dev/null
    -o LogLevel=ERROR
    -o ServerAliveInterval=1
    -o ServerAliveCountMax=2
)

remote_hostname() {
    ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" 'hostname -s' 2>/dev/null
}

verify_remote_identity() {
    local remote_name="$1"
    [[ "${remote_name,,}" == "${VMNAME,,}" ]] ||
        fail "SSH reached '$remote_name' instead of the selected host '$VMNAME'."
}

send_wol_packet() {
    command -v python3 >/dev/null 2>&1 || fail "Required command not found: python3"

    python3 - "$MAC_ADDRESS" "$WOL_BROADCAST" "$WOL_PORT" <<'PY'
import socket
import sys

mac = bytes.fromhex(sys.argv[1].replace(":", ""))
packet = b"\xff" * 6 + mac * 16
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
    sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sender.sendto(packet, (sys.argv[2], int(sys.argv[3])))
print(f"Magic packet sent to {sys.argv[1]} via {sys.argv[2]}:{sys.argv[3]}.")
PY
}

wake_host() {
    local was_reachable=0
    local remote_name=""

    if remote_name="$(remote_hostname)"; then
        verify_remote_identity "$remote_name"
        was_reachable=1
    fi

    send_wol_packet
    if (( was_reachable )); then
        log "$VMNAME was already reachable over SSH; the packet was sent, but no wake transition was needed."
        return 0
    fi

    log "Waiting for $VMNAME to respond over SSH after Wake-on-LAN."
    for ((attempt = 1; attempt <= 30; attempt++)); do
        if remote_name="$(remote_hostname)"; then
            verify_remote_identity "$remote_name"
            log "WAKE VERIFIED: $VMNAME responded over SSH as $remote_name."
            return 0
        fi
        if (( attempt % 5 == 0 )); then
            log "Still waiting for $VMNAME (${attempt}/30)."
        fi
        sleep 2
    done

    fail "Wake packet was sent, but $VMNAME did not respond over SSH within 120 seconds."
}

sleep_host() {
    local remote_name=""
    local request_status=0
    local consecutive_failures=0

    remote_name="$(remote_hostname)" ||
        fail "$VMNAME is not reachable over SSH; wake it before requesting sleep."
    verify_remote_identity "$remote_name"

    ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" \
        'grep -qw mem /sys/power/state && grep -Fq "[deep]" /sys/power/mem_sleep' \
        >/dev/null 2>&1 ||
        fail "$VMNAME does not report deep suspend-to-RAM as its selected sleep mode."

    ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" \
        'sudo -n -l /usr/bin/systemctl --no-block suspend >/dev/null' \
        >/dev/null 2>&1 ||
        fail "Rundeck lacks passwordless permission for systemctl --no-block suspend on $VMNAME."

    log "Requesting suspend-to-RAM on $VMNAME."
    ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" \
        'sudo -n /usr/bin/systemctl --no-block suspend' || request_status=$?
    log "Suspend request returned status ${request_status}; checking SSH availability."

    sleep 5
    for ((attempt = 1; attempt <= 20; attempt++)); do
        if ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" true >/dev/null 2>&1; then
            consecutive_failures=0
            if (( attempt % 5 == 0 )); then
                log "$VMNAME remains reachable (${attempt}/20 checks)."
            fi
        else
            consecutive_failures=$((consecutive_failures + 1))
            if (( consecutive_failures >= 3 )); then
                log "SLEEP VERIFIED: $VMNAME became unreachable over SSH for three consecutive checks after the suspend request."
                return 0
            fi
        fi
        sleep 2
    done

    fail "$VMNAME remained reachable over SSH; suspend-to-RAM was not verified."
}

case "$ACTION" in
    wake) wake_host ;;
    sleep) sleep_host ;;
esac