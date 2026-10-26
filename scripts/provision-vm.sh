#!/usr/bin/env bash
set -Eeuo pipefail

# Provision a new Debian VM from Proxmox template 9999.
# Run as root on the Proxmox host.

TEMPLATE_ID="${TEMPLATE_ID:-9999}"
VM_CREATED=0

VMID=""
NAME=""
CORES=""
MEMORY=""
DISK=""

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

fail() {
    log "ERROR: $*" >&2
    exit 1
}

usage() {
    clear
    cat <<EOF
Usage: $0 <vmid> <vm-name> [OPTIONS]

Required Parameters:
  VM ID                 Unique Proxmox VM ID (e.g. 100-999999)
  VM name               Name / hostname for the new VM

Optional Parameters:
  --cores <num>         Number of CPU cores (default: inherit from template)
  --memory <GB>         RAM in GB (default: inherit from template)
  --disk <GB>           Disk size in GB (default: inherit from template)
  --help                Show this usage message

Examples:
  $0 105 web-server-01
  $0 105 web-server-01 --cores 2 --memory 2 --disk 20
  $0 105 web-server-01 --memory 1
EOF
    exit 0
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

# Parse command line options and arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            usage
            ;;
        --cores)
            [[ $# -ge 2 ]] || fail "Option '--cores' requires an argument."
            CORES="$2"
            shift 2
            ;;
        --cores=*)
            CORES="${1#*=}"
            shift
            ;;
        --memory)
            [[ $# -ge 2 ]] || fail "Option '--memory' requires an argument."
            MEMORY="$2"
            shift 2
            ;;
        --memory=*)
            MEMORY="${1#*=}"
            shift
            ;;
        --disk)
            [[ $# -ge 2 ]] || fail "Option '--disk' requires an argument."
            DISK="$2"
            shift 2
            ;;
        --disk=*)
            DISK="${1#*=}"
            shift
            ;;
        --)
            shift
            break
            ;;
        -*)
            fail "Unknown option: $1 (run with --help for usage)"
            ;;
        *)
            if [[ -z "$VMID" ]]; then
                VMID="$1"
            elif [[ -z "$NAME" ]]; then
                NAME="$1"
            else
                fail "Unexpected positional argument: $1 (run with --help for usage)"
            fi
            shift
            ;;
    esac
done

[[ $EUID -eq 0 ]] || fail "Run this script as root on the Proxmox host."

for cmd in qm jq awk; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: $cmd"
done

# Validate required parameters
[[ -n "$VMID" ]] || fail "Missing required parameter: VM ID (run with --help for usage)."
[[ -n "$NAME" ]] || fail "Missing required parameter: VM name (run with --help for usage)."

[[ "$VMID" =~ ^[1-9][0-9]{1,5}$ ]] ||
    fail "Invalid VM ID '${VMID}'. Must be a positive integer (e.g., 100-999999)."

[[ "$NAME" =~ ^[a-zA-Z0-9]([a-zA-Z0-9._-]{0,61}[a-zA-Z0-9])?$ ]] ||
    fail "Invalid VM name '${NAME}'. Must be a valid hostname (alphanumeric, dots, dashes, underscores)."

if [[ -n "$CORES" ]]; then
    [[ "$CORES" =~ ^[1-9][0-9]*$ ]] ||
        fail "Invalid CPU cores value '${CORES}'. Must be a positive integer."
fi

if [[ -n "$MEMORY" ]]; then
    [[ "$MEMORY" =~ ^[1-9][0-9]*$ ]] ||
        fail "Invalid memory value '${MEMORY}'. Must be a positive integer in GB."
    (( MEMORY >= 1 )) ||
        fail "Memory must be at least 1 GB (got: ${MEMORY})."
fi
MEMORY=$(( $MEMORY * 1024 ))

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

# Apply optional CPU cores, disk or memory overrides if specified
if [[ -n "$CORES" || -n "$MEMORY" || -n "$DISK" ]]; then
    QM_SET_ARGS=()
    if [[ -n "$CORES" ]]; then
        log "Setting CPU cores to ${CORES}..."
        QM_SET_ARGS+=(--cores "$CORES")
    fi
    if [[ -n "$MEMORY" ]]; then
        log "Setting RAM memory to ${MEMORY} MB..."
        QM_SET_ARGS+=(--memory "$MEMORY")
    fi
    if [[ -n "$DISK" ]]; then
        log "Resizing disk to ${DISK}..."
        qm resize "$VMID" scsi0 "$DISK"
    fi
    if [[ ${#QM_SET_ARGS[@]} -gt 0 ]]; then
        qm set "$VMID" "${QM_SET_ARGS[@]}"
    fi
fi

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
log "Cores: $(qm config "$VMID" | awk '/^cores:/ {print $2}')"
log "Memory: $(qm config "$VMID" | awk '/^memory:/ {print $2}') MB"
log "Disk: $(qm config "$VMID" | awk '/^scsi0:/ {print $2}')"
if [[ -n "$IP_ADDRESS" ]]; then
    log "IPv4 Address (DHCP): ${IP_ADDRESS}"
    log "SSH Access: ssh ian@${IP_ADDRESS}"
else
    log "IPv4 Address: Pending DHCP lease (check with: qm guest cmd ${VMID} network-get-interfaces)"
fi
log "Source template ${TEMPLATE_ID} preserved."
log "=================================================="

VM_CREATED=0
