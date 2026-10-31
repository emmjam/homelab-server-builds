#!/bin/bash
set -Eeuo pipefail

# Delete one Proxmox VM by numeric VM ID or exact VM name.
# Run as root on the Proxmox host.

TARGET="${1:-}"

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

fail() {
    log "ERROR: $*" >&2
    exit 1
}

[[ $EUID -eq 0 ]] || fail "Run this script as root on the Proxmox host."
command -v qm >/dev/null 2>&1 || fail "Required command not found: qm"
[[ -n "$TARGET" ]] || fail "Provide a VM name or numeric VM ID."

VMID=""
if [[ "$TARGET" =~ ^[1-9][0-9]{0,5}$ ]]; then
    VMID="$TARGET"
else
    [[ "$TARGET" =~ ^[a-zA-Z0-9]([a-zA-Z0-9._-]{0,61}[a-zA-Z0-9])?$ ]] ||
        fail "Invalid VM name '$TARGET'."

    mapfile -t VM_IDS < <(qm list | awk 'NR > 1 && $1 ~ /^[0-9]+$/ { print $1 }')
    MATCHES=()
    for candidate_id in "${VM_IDS[@]}"; do
        candidate_name="$(qm config "$candidate_id" | sed -n 's/^name: //p' | head -n 1)"
        [[ "$candidate_name" == "$TARGET" ]] && MATCHES+=("$candidate_id")
    done

    ((${#MATCHES[@]} == 1)) || {
        if ((${#MATCHES[@]} == 0)); then
            fail "No VM with exact name '$TARGET' was found."
        else
            fail "More than one VM has the exact name '$TARGET'; delete by VM ID instead."
        fi
    }
    VMID="${MATCHES[0]}"
fi

qm status "$VMID" >/dev/null 2>&1 || fail "VM ID ${VMID} does not exist."
VM_CONFIG="$(qm config "$VMID")" || fail "Could not read configuration for VM ${VMID}."
VM_NAME="$(printf '%s\n' "$VM_CONFIG" | sed -n 's/^name: //p' | head -n 1)"

case "$VMID" in
    9000|9999) fail "Refusing to delete protected template VM ${VMID} (${VM_NAME})." ;;
esac
if grep -Fxq 'template: 1' <<< "$VM_CONFIG"; then
    fail "Refusing to delete VM ${VMID} (${VM_NAME}); it is marked as a template."
fi

STATUS="$(qm status "$VMID" | awk '{print $2}')"
if [[ "$STATUS" == "running" ]]; then
    log "Stopping VM ${VMID} (${VM_NAME}) immediately with qm stop."
    qm stop "$VMID" --timeout 30 ||
        fail "Could not stop VM ${VMID}; it was not deleted."
    STATUS="$(qm status "$VMID" | awk '{print $2}')"
    [[ "$STATUS" == "stopped" ]] || fail "VM ${VMID} is still '$STATUS'; it was not deleted."
fi

log "Deleting VM ${VMID} (${VM_NAME}) and purging its disks."
qm destroy "$VMID" --purge 1 || fail "Proxmox failed to delete VM ${VMID}."
qm status "$VMID" >/dev/null 2>&1 && fail "VM ${VMID} still exists after qm destroy."
log "VM ${VMID} (${VM_NAME}) was deleted successfully."
