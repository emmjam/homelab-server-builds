#!/bin/bash
set -Eeuo pipefail

PVE_HOST="192.168.0.101"
DEST="rundeck@$PVE_HOST"
REMOTE_SCRIPT="/opt/homelab-server-builds/scripts/provision-vm.sh"
SSH_KEY="/var/lib/rundeck/.ssh/target_ed25519"
TEMPLATE_ID="9000"
VMNAME="$RD_OPTION_VMNAME"
CORES="${RD_OPTION_CORES:-}"
MEMORY="${RD_OPTION_MEMORY:-}"
DISK="${RD_OPTION_DISK:-}"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[[ -r "$SSH_KEY" ]] || fail "Rundeck SSH key is missing or unreadable: $SSH_KEY"
command -v ssh >/dev/null 2>&1 || fail "Required command not found: ssh"
[[ -n "$VMNAME" ]] || fail "Missing required VM name."
[[ "$VMNAME" =~ ^[a-zA-Z0-9]([a-zA-Z0-9._-]{0,61}[a-zA-Z0-9])?$ ]] ||
    fail "Invalid VM name '$VMNAME'."

SCRIPT_ARGS=("$VMNAME")
if [[ -n ${RD_OPTION_ID:-} ]]; then SCRIPT_ARGS+=(--id "$RD_OPTION_ID"); fi
if [[ ${RD_OPTION_DIRECT_APT:-false} == true ]]; then SCRIPT_ARGS+=(--direct-apt); fi
if [[ -n "$CORES" ]]; then SCRIPT_ARGS+=(--cores "$CORES"); fi
if [[ -n "$MEMORY" ]]; then SCRIPT_ARGS+=(--memory "$MEMORY"); fi
if [[ -n "$DISK" ]]; then SCRIPT_ARGS+=(--disk "$DISK"); fi

REMOTE_COMMAND="sudo -n $(printf '%q' "$REMOTE_SCRIPT")"
for arg in "${SCRIPT_ARGS[@]}"; do
    REMOTE_COMMAND+=" $(printf '%q' "$arg")"
done

printf 'Starting VM provisioning: name=%s, template=%s' "$VMNAME" "$TEMPLATE_ID"
[[ -z "$CORES" ]] || printf ' , CPU=%s cores' "$CORES"
[[ -z "$MEMORY" ]] || printf ' , RAM=%s GB' "$MEMORY"
[[ -z "$DISK" ]] || printf ' , disk=%s GB' "$DISK"
printf '\nProxmox will assign the lowest available VM ID.\n'
printf 'Calling %s on %s with the requested parameters.\n' "$REMOTE_SCRIPT" "$PVE_HOST"

ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=10 "$DEST" "$REMOTE_COMMAND" ||
    fail "Remote provisioning failed for VM '$VMNAME'; see the command output above."

printf 'Provisioning completed for VM %s. Check the remote output above for the assigned VM ID and status.\n' "$VMNAME"
