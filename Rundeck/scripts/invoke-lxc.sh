#!/bin/bash
# Remote commands use fixed paths and shell-quoted arguments assembled locally.
# shellcheck disable=SC2029
set -Eeuo pipefail
MODE=${1:-}
REPO=/opt/homelab-server-builds
DEST=rundeck@192.168.0.101
STAGING=/home/rundeck/homelab-lxc-staging
KEY=/var/lib/rundeck/.ssh/target_ed25519
SSH=( -i "$KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 )
case $MODE in
    build) SCRIPT=build-template.sh; OPTIONS=(template_id storage image_storage bridge);;
    create) SCRIPT=create-container.sh; OPTIONS=(id hostname cores memory disk storage bridge ip gateway dns search_domain template_id ssh_public_key);;
    delete) SCRIPT=delete-container.sh; OPTIONS=(id confirm);;
    *) echo 'Unsupported LXC action' >&2; exit 1;;
esac
[[ -r $KEY ]] || { echo 'Missing Rundeck SSH key' >&2; exit 1; }
TEMP=$(mktemp -d)
trap 'rm -rf -- "$TEMP"' EXIT
cd "$REPO"
FILES=(lxc Ansible/ansible.cfg Ansible/playbooks/debian-lxc.yml Ansible/roles/debian_lxc Ansible/connection_plugins/pct.py)
# Stage only the LXC code. No secrets, unrelated playbooks or existing VM scripts.
tar --exclude='__pycache__' -cf "$TEMP/lxc.tar" "${FILES[@]}"
find lxc Ansible/roles/debian_lxc -type f ! -path '*/__pycache__/*' -print > "$TEMP/files"
printf '%s\n' Ansible/ansible.cfg Ansible/playbooks/debian-lxc.yml Ansible/connection_plugins/pct.py >> "$TEMP/files"
while IFS= read -r file; do sha256sum "$file"; done < "$TEMP/files" > "$TEMP/manifest"
ssh "${SSH[@]}" "$DEST" "mkdir -p '$STAGING'"
scp "${SSH[@]}" "$TEMP/lxc.tar" "$TEMP/manifest" "$DEST:$STAGING/"
ssh "${SSH[@]}" "$DEST" "tar -xf '$STAGING/lxc.tar' -C '$STAGING'; cd /opt/homelab-lxc; sha256sum -c '$STAGING/manifest'" || {
    echo "Installed LXC code is missing or outdated. Administrator: sudo bash $STAGING/lxc/install.sh" >&2
    exit 1
}
ARGS=()
for option in "${OPTIONS[@]}"; do
    variable="RD_OPTION_${option^^}"
    value=${!variable:-}
    [[ -z $value ]] || ARGS+=("--${option//_/-}" "$value")
done
REMOTE="sudo -n /opt/homelab-lxc/lxc/$SCRIPT"
for arg in "${ARGS[@]}"; do REMOTE+=" $(printf '%q' "$arg")"; done
ssh "${SSH[@]}" "$DEST" "$REMOTE"
