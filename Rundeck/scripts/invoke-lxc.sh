#!/bin/bash
# Remote commands use fixed paths and shell-quoted arguments assembled locally.
# shellcheck disable=SC2029
set -Eeuo pipefail
MODE=${1:-}
REPO=/opt/homelab-server-builds
DEST=rundeck@192.168.0.101
REMOTE_REPO=/opt/homelab-server-builds
KEY=/var/lib/rundeck/.ssh/target_ed25519
SSH=( -i "$KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 )
case $MODE in
    deploy) SCRIPT=''; OPTIONS=();;
    build) SCRIPT=build-template.sh; OPTIONS=(template_id storage image_storage bridge);;
    create) SCRIPT=create-container.sh; OPTIONS=(id hostname cores memory disk storage bridge ip gateway dns search_domain template_id ssh_public_key);;
    delete) SCRIPT=delete-container.sh; OPTIONS=(id confirm);;
    *) echo 'Unsupported LXC action' >&2; exit 1;;
esac
[[ -r $KEY ]] || { echo 'Missing Rundeck SSH key' >&2; exit 1; }
# Serialize transfer and execution so a second job cannot overwrite running code.
exec 9>/tmp/homelab-lxc-dispatch.lock
flock -n 9 || { echo 'Another LXC job is running' >&2; exit 1; }
TEMP=$(mktemp -d)
ACTIVE_CANDIDATE=''
cleanup() {
    local rc=$?
    trap - EXIT
    if [[ -n $ACTIVE_CANDIDATE ]]; then
        ssh "${SSH[@]}" "$DEST" "sudo -n $REMOTE_REPO/scripts/build-template.sh --abort $ACTIVE_CANDIDATE" ||
            echo "WARNING: inspect unfinished build candidate $ACTIVE_CANDIDATE" >&2
    fi
    rm -rf -- "$TEMP"
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cd "$REPO"
# Normal jobs run the existing deployment job before this execution step.
if [[ $MODE == deploy ]]; then
    bash "$REPO/Rundeck/scripts/deploy-build-scripts-to-tnas.sh"
    exit 0
fi
ARGS=()
for option in "${OPTIONS[@]}"; do
    variable="RD_OPTION_${option^^}"
    value=${!variable:-}
    [[ -z $value ]] || ARGS+=("--${option//_/-}" "$value")
done
if [[ $MODE == build ]]; then
    command -v ansible-playbook >/dev/null || { echo 'Install ansible-core on the Rundeck host' >&2; exit 1; }
    REMOTE="sudo -n $REMOTE_REPO/scripts/$SCRIPT --prepare"
else
    REMOTE="sudo -n $REMOTE_REPO/scripts/$SCRIPT"
fi
for arg in "${ARGS[@]}"; do REMOTE+=" $(printf '%q' "$arg")"; done
if [[ $MODE != build ]]; then
    ssh "${SSH[@]}" "$DEST" "$REMOTE"
    exit 0
fi
ssh "${SSH[@]}" "$DEST" "$REMOTE" | tee "$TEMP/prepare.log"
ACTIVE_CANDIDATE=$(sed -n 's/^LXC_CANDIDATE_ID=//p' "$TEMP/prepare.log")
[[ $ACTIVE_CANDIDATE =~ ^[1-9][0-9]{2,5}$ ]] || { echo 'Missing valid build candidate ID' >&2; exit 1; }
printf '[lxc]\n%s ansible_connection=pct ansible_python_interpreter=/usr/bin/python3\n' "$ACTIVE_CANDIDATE" > "$TEMP/inventory"
export ANSIBLE_CONFIG="$REPO/Ansible/ansible.cfg"
export ANSIBLE_CONNECTION_PLUGINS="$REPO/Ansible/connection_plugins"
export ANSIBLE_ROLES_PATH="$REPO/Ansible/roles"
export ANSIBLE_LOCAL_TEMP="$TEMP/ansible"
log_message='Applying Debian LXC baseline from the Rundeck Ansible controller'
printf '%s\n' "$log_message"
apply_baseline() {
    if ansible-playbook -i "$TEMP/inventory" "$REPO/Ansible/playbooks/debian-lxc.yml"; then return 0; fi
    # Collect guest-side failure details before the existing cleanup trap removes it.
    local diagnostic
    diagnostic=$(printf '%s' '/usr/sbin/sshd -t; systemctl --no-pager --full status ssh; journalctl --no-pager -u ssh -n 40' | base64 -w0)
    ssh "${SSH[@]}" "$DEST" "sudo -n $REMOTE_REPO/scripts/build-template.sh --ansible-exec $ACTIVE_CANDIDATE $diagnostic" || true
    return 1
}
apply_baseline
ANSIBLE_NOCOLOR=1 apply_baseline | tee "$TEMP/repeat.log"
grep -Eq 'changed=0[[:space:]]+unreachable=0[[:space:]]+failed=0' "$TEMP/repeat.log" || { echo 'Baseline is not idempotent' >&2; exit 1; }
ssh "${SSH[@]}" "$DEST" "sudo -n $REMOTE_REPO/scripts/build-template.sh --complete $ACTIVE_CANDIDATE"
ACTIVE_CANDIDATE=''
