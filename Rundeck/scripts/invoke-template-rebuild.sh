#!/bin/bash
set -Eeuo pipefail

PVE_HOST="192.168.0.101"
DEST="rundeck@$PVE_HOST"
REMOTE_SCRIPT="/opt/homelab-server-builds/scripts/rebuild-debian-template.sh"
SSH_KEY="/var/lib/rundeck/.ssh/target_ed25519"

[[ -r "$SSH_KEY" ]] || {
    echo "ERROR: SSH key missing or unreadable: $SSH_KEY" >&2
    exit 1
}

command -v ssh >/dev/null 2>&1 || {
    echo "ERROR: ssh not found." >&2
    exit 1
}

REMOTE_COMMAND="sudo -n $(printf '%q' "$REMOTE_SCRIPT")"

echo "Starting Debian template rebuild on TNAS..."

ssh -i "$SSH_KEY" \
    -o BatchMode=yes \
    -o ConnectTimeout=10 \
    "$DEST" "$REMOTE_COMMAND"

echo "Debian template rebuild completed."
