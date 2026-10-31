#!/bin/bash
set -Eeuo pipefail

# Local checkout on the Rundeck server.
REPO="/opt/homelab-server-builds"

# Destination on TNAS.
DEST="rundeck@192.168.0.101"
REMOTE_REPO="/opt/homelab-server-builds"

# SSH key installed for the Rundeck service account.
SSH_KEY="/var/lib/rundeck/.ssh/target_ed25519"

SSH_OPTS=(
    -i "$SSH_KEY"
    -o BatchMode=yes
    -o IdentitiesOnly=yes
    -o StrictHostKeyChecking=yes
)

# Verify the source scripts exist in the local checkout.
for file in Rundeck/scripts/rebuild-debian-template.sh scripts/debian-baseline.sh Rundeck/scripts/provision-vm.sh; do
    if [[ ! -s "$REPO/$file" ]]; then
        echo "ERROR: Missing source script: $REPO/$file" >&2
        exit 1
    fi
done

# Verify SSH key exists and is readable.
if [[ ! -r "$SSH_KEY" ]]; then
    echo "ERROR: SSH key is missing or unreadable: $SSH_KEY" >&2
    exit 1
fi

# Ensure destination directories exist on TNAS.
ssh "${SSH_OPTS[@]}" "$DEST" \
    "mkdir -p '$REMOTE_REPO/scripts'"

# Copy scripts from the local checkout to TNAS.
scp "${SSH_OPTS[@]}" \
    "$REPO/Rundeck/scripts/rebuild-debian-template.sh" \
    "$DEST:$REMOTE_REPO/scripts/rebuild-debian-template.sh"

scp "${SSH_OPTS[@]}" \
    "$REPO/scripts/debian-baseline.sh" \
    "$DEST:$REMOTE_REPO/debian-baseline.sh"

scp "${SSH_OPTS[@]}" \
    "$REPO/Rundeck/scripts/provision-vm.sh" \
    "$DEST:$REMOTE_REPO/scripts/provision-vm.sh"

# Set executable permissions and verify the deployed files.
ssh "${SSH_OPTS[@]}" "$DEST" \
    "set -eu
     chmod 700 '$REMOTE_REPO/scripts/rebuild-debian-template.sh'
     chmod 700 '$REMOTE_REPO/debian-baseline.sh'
     chmod 700 '$REMOTE_REPO/scripts/provision-vm.sh'
     test -s '$REMOTE_REPO/scripts/rebuild-debian-template.sh'
     test -s '$REMOTE_REPO/debian-baseline.sh'
     test -s '$REMOTE_REPO/scripts/provision-vm.sh'"

echo "Deployment completed and destination files verified."
