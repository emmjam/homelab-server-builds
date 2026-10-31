#!/bin/bash
set -Eeuo pipefail

PVE_HOST="192.168.0.101"
DEST="rundeck@$PVE_HOST"
REMOTE_SCRIPT="/opt/homelab-server-builds/scripts/delete-vm.sh"
SSH_KEY="/var/lib/rundeck/.ssh/target_ed25519"
TARGET="${RD_OPTION_TARGET:-}"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[[ -r "$SSH_KEY" ]] || fail "Rundeck SSH key is missing or unreadable: $SSH_KEY"
command -v ssh >/dev/null 2>&1 || fail "Required command not found: ssh"
[[ -n "$TARGET" ]] || fail "Provide a VM name or numeric VM ID."

REMOTE_COMMAND="sudo -n $(printf '%q' "$REMOTE_SCRIPT") $(printf '%q' "$TARGET")"

printf 'Requesting deletion of Proxmox VM target: %s\n' "$TARGET"
ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=10 "$DEST" "$REMOTE_COMMAND" ||
    fail "Remote deletion failed for VM target '$TARGET'; see the command output above."

printf 'Proxmox deletion completed for target %s.\n' "$TARGET"
