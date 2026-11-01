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
for file in Rundeck/scripts/rebuild-debian-template.sh scripts/debian-baseline.sh Rundeck/scripts/provision-vm.sh Rundeck/scripts/delete-vm.sh Rundeck/scripts/build-template.sh Rundeck/scripts/common.sh Rundeck/scripts/create-container.sh Rundeck/scripts/delete-container.sh; do
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

scp "${SSH_OPTS[@]}" \
    "$REPO/Rundeck/scripts/delete-vm.sh" \
    "$DEST:$REMOTE_REPO/scripts/delete-vm.sh"

# LXC scripts use the same flat source and TNAS destination pattern as VM scripts.
for script in build-template.sh common.sh create-container.sh delete-container.sh; do
    scp "${SSH_OPTS[@]}" "$REPO/Rundeck/scripts/$script" "$DEST:$REMOTE_REPO/scripts/$script"
done

# Set executable permissions and verify the deployed files.
ssh "${SSH_OPTS[@]}" "$DEST" \
    "set -eu
     chmod 700 '$REMOTE_REPO/scripts/rebuild-debian-template.sh'
     chmod 700 '$REMOTE_REPO/debian-baseline.sh'
     chmod 700 '$REMOTE_REPO/scripts/provision-vm.sh'
     chmod 700 '$REMOTE_REPO/scripts/delete-vm.sh'
     test -s '$REMOTE_REPO/scripts/rebuild-debian-template.sh'
     test -s '$REMOTE_REPO/debian-baseline.sh'
     test -s '$REMOTE_REPO/scripts/provision-vm.sh'
     test -s '$REMOTE_REPO/scripts/delete-vm.sh'
     chmod 700 '$REMOTE_REPO/scripts/build-template.sh'
     test -s '$REMOTE_REPO/scripts/build-template.sh'
     chmod 700 '$REMOTE_REPO/scripts/common.sh'
     test -s '$REMOTE_REPO/scripts/common.sh'
     chmod 700 '$REMOTE_REPO/scripts/create-container.sh'
     test -s '$REMOTE_REPO/scripts/create-container.sh'
     chmod 700 '$REMOTE_REPO/scripts/delete-container.sh'
     test -s '$REMOTE_REPO/scripts/delete-container.sh'"

echo "Deployment completed and destination files verified."
