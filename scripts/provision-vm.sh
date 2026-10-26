#!/usr/bin/env bash
set -Eeuo pipefail

# Provision a new Debian VM from Proxmox template 9999.
# Run as root on the Proxmox host.

TEMPLATE_ID="${TEMPLATE_ID:-9999}"
VM_CREATED=0

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

fail() {
    log "ERROR: $*" >&2
    exit 1
}

usage() {
    cat <<EOF >&2
Usage: $0 <vmid> <vm-name>

Arguments:
  <vmid>    Numeric ID for the new VM (e.g., 100-999999)
  <vm-name> Hostname / name for the new VM

Example:
  $0 105 web-server-01
EOF
    exit 2
}

cleanup() {
    local rc=$?
    trap - EXIT

    if (( rc != 0 && VM_CREATED )); then
        log "Provisioning failed. Cleaning up partial VM ${VMID}..."
        qm stop "$VMID" --timeout 30 >/dev/null 2>&1 || true
        qm destroy "$VMID" --purge 1 >/dev/null 2>&1 || true
        log "Partial VM ${VMID} removed. Source template ${TEMPLATE_ID} is untouched."
    fi

    exit "$rc"
}
trap cleanup EXIT

[[ $EUID -eq 0 ]] || fail "Run this script as root on the Proxmox host."

for cmd in qm jq awk; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: $cmd"
done

[[ $# -eq 2 ]] || usage

VMID="$1"
NAME="$2"

# Input validation
[[ "$VMID" =~ ^[1-9][0-9]{1,5}$ ]] ||
    fail "Invalid VM ID '${VMID}'. Must be a positive integer (e.g., 100-999999)."

[[ "$NAME" =~ ^[a-zA-Z0-9]([a-zA-Z0-9._-]{0,61}[a-zA-Z0-9])?$ ]] ||
    fail "Invalid VM name '${NAME}'. Must be a valid hostname (alphanumeric, dots, dashes, underscores)."

# Template verification
qm status "$TEMPLATE_ID" >/dev/null 2>&1 ||
    fail "Source template VM ${TEMPLATE_ID} does not exist."

qm config "$TEMPLATE_ID" | grep -q '^template: 1$' ||
    fail "VM ${TEMPLATE_ID} is not marked as a Proxmox template."

# Conflict checks
if qm status "$VMID" >/dev/null 2>&1; then
    fail "VM ID ${VMID} already exists. Rejecting to prevent overwriting existing VMs."
fi

if qm list | awk -v name="$NAME" '$2 == name { found=1 } END { exit !found }'; then
    fail "A VM named '${NAME}' already exists. Choose a unique name."
fi

# Clone template (inherits Cloud-Init DHCP and SSH configuration)
log "Cloning template ${TEMPLATE_ID} to new VM ${VMID} (${NAME})..."
qm clone "$TEMPLATE_ID" "$VMID" --name "$NAME" --full 1
VM_CREATED=1

# Start VM
log "Starting VM ${VMID} (${NAME})..."
qm start "$VMID"

# Report VM status and wait for network address
log "Waiting for VM ${VMID} to boot and acquire network address..."
IP_ADDRESS=""
for ((i=1; i<=30; i++)); do
    IP_ADDRESS="$(qm guest cmd "$VMID" network-get-interfaces 2>/dev/null | jq -r '
        .[]? | select(.name != "lo") | .["ip-addresses"][]? |
        select(.["ip-address-type"] == "ipv4" and (.["ip-address"] | startswith("127.") | not)) |
        .["ip-address"]
    ' 2>/dev/null | head -n 1 || true)"

    if [[ "$IP_ADDRESS" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        break
    fi
    sleep 3
done

log "=================================================="
log "VM ${VMID} (${NAME}) provisioned successfully!"
log "Status: $(qm status "$VMID" | awk '{print $2}')"
if [[ -n "$IP_ADDRESS" ]]; then
    log "IPv4 Address (DHCP): ${IP_ADDRESS}"
    log "SSH Access: ssh ian@${IP_ADDRESS}"
else
    log "IPv4 Address: Pending DHCP lease (check with: qm guest cmd ${VMID} network-get-interfaces)"
fi
log "Source template ${TEMPLATE_ID} preserved."
log "=================================================="

VM_CREATED=0
