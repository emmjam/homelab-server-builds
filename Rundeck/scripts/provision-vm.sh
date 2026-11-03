#!/bin/bash
set -Eeuo pipefail

# Update metadata on the existing stopped VM template without booting it.
if [[ ${1:-} == --configure-template-dns ]]; then
    [[ $# == 1 && $EUID == 0 ]] || exit 1
    qm config 9000 | grep -qx 'template: 1'
    qm set 9000 --nameserver 192.168.0.2 --delete searchdomain
    exit 0
fi

# Explicitly requested service-ID migration, separate from template provisioning.
if [[ ${1:-} == --relocate-service ]]; then
    [[ $# == 3 && $EUID == 0 ]] || { echo 'Expected source and destination IDs as root'; exit 1; }
    source_id=$2 target_id=$3
    case "$source_id:$target_id" in
        9001:112) service_name=Apt-Cache; service_unit=apt-cacher-ng;;
        9002:113) service_name=rundeck; service_unit=rundeckd;;
        *) echo 'Unapproved service migration pair'; exit 1;;
    esac
    exec 8>/run/lock/homelab-service-migration.lock
    flock -n 8 || { echo 'Service migration already running'; exit 1; }
    config=$(qm config "$source_id")
    grep -qx "name: $service_name" <<< "$config" || { echo 'Unexpected source VM'; exit 1; }
    ! grep -qx 'template: 1' <<< "$config" || exit 1
    ! grep -qx 'protection: 1' <<< "$config" || exit 1
    pvesh get /cluster/resources --output-format json | jq -e --argjson id "$target_id" 'all(.[]; .vmid != $id)' >/dev/null || { echo 'Destination ID occupied'; exit 1; }
    qm agent "$source_id" ping
    stopped_source=0 cloned_target=0
    # Invoked by the EXIT trap.
    # shellcheck disable=SC2329
    rollback_service() {
        rc=$?
        trap - EXIT
        if ((rc && stopped_source)); then
            if ((cloned_target)); then qm stop "$target_id" --timeout 30 || exit "$rc"; fi
            qm start "$source_id" || true
            echo 'Migration failed; original VM restarted, destination retained for inspection'
        fi
        exit "$rc"
    }
    trap rollback_service EXIT
    qm shutdown "$source_id" --timeout 120
    qm status "$source_id" | grep -qx 'status: stopped'
    stopped_source=1
    qm clone "$source_id" "$target_id" --full 1 --name "$service_name"
    cloned_target=1
    # Preserve DHCP reservations and the existing network identity while IDs change.
    while IFS= read -r line; do
        [[ $line =~ ^(net[0-9]+):\ (.*)$ ]] || continue
        qm set "$target_id" "--${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    done <<< "$config"
    qm start "$target_id"
    ready=0
    for ((attempt=0;attempt<90;attempt++)); do
        if qm agent "$target_id" ping >/dev/null 2>&1; then
            result=$(qm guest exec "$target_id" --timeout 30 -- systemctl is-active "$service_unit" 2>/dev/null || true)
            if jq -e '.exitcode == 0' <<< "$result" >/dev/null 2>&1; then ready=1; break; fi
        fi
        sleep 3
    done
    ((ready)) || { echo 'Destination service did not become healthy'; exit 1; }
    qm status "$source_id" | grep -qx 'status: stopped'
    qm destroy "$source_id" --purge 1
    stopped_source=0
    echo "SUCCESS: $service_name moved from $source_id to $target_id; $service_unit active"
    exit 0
fi

# Provision a new Debian VM from Proxmox template 9000.
# Run as root on the Proxmox host.

TEMPLATE_ID="${TEMPLATE_ID:-9000}"
VM_CREATED=0

NAME=""
REQUESTED_ID=""
DIRECT_APT=0
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
Usage: $0 <vm-name> [OPTIONS]

Required Parameters:
  VM name               Name / hostname for the new VM; Proxmox assigns the lowest available VM ID

Optional Parameters:
  --id <num>           Explicit unused VM ID (default: next available)
  --direct-apt         Bootstrap a cache server without an existing APT proxy
  --cores <num>         Number of CPU cores (default: inherit from template)
  --memory <GB>         RAM in GB (default: inherit from template)
  --disk <GB>           Disk size in GB (default: inherit from template)
  --help                Show this usage message

Examples:
  $0 web-server-01
  $0 web-server-01 --cores 2 --memory 2 --disk 20
  $0 web-server-01 --memory 1
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
        --id)
            [[ $# -ge 2 ]] || fail 'Missing VM ID'
            REQUESTED_ID=$2
            shift 2;;
        --direct-apt)
            DIRECT_APT=1
            shift;;
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
            if [[ -z "$NAME" ]]; then
                NAME="$1"
            else
                fail "Unexpected positional argument: $1 (run with --help for usage)"
            fi
            shift
            ;;
    esac
done

[[ $EUID -eq 0 ]] || fail "Run this script as root on the Proxmox host."

for cmd in qm pvesh jq awk; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: $cmd"
done

# Validate required parameters
[[ -n "$NAME" ]] || fail "Missing required parameter: VM name (run with --help for usage)."

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

# Ask Proxmox to select the lowest available VM ID. Keep the returned ID
# numeric and within the supported range before using it in qm commands.
if [[ -n $REQUESTED_ID ]]; then
    [[ $REQUESTED_ID =~ ^[1-9][0-9]{2,5}$ && $REQUESTED_ID -lt 9000 ]] || fail 'Explicit VM ID must be between 100 and 8999'
    pvesh get /cluster/resources --output-format json | jq -e --argjson id "$REQUESTED_ID" 'all(.[]; .vmid != $id)' >/dev/null || fail 'Requested VM ID is occupied'
    VMID=$REQUESTED_ID
else
VMID="$(pvesh get /cluster/nextid 2>/dev/null)" ||
    fail "Could not obtain the next available VM ID from Proxmox."
VMID="$(printf '%s' "$VMID" | tr -d '\r\n')"
[[ "$VMID" =~ ^[1-9][0-9]{1,5}$ ]] ||
    fail "Proxmox returned an invalid next VM ID: '${VMID}'."
log "Proxmox selected the lowest available VM ID: ${VMID}."
fi

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
qm set "$VMID" --net0 virtio,bridge=vmbr0 --ipconfig0 ip=dhcp \
    --nameserver 192.168.0.2 --delete searchdomain

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
        log "Resizing disk to ${DISK} Gb..."
        qm resize "$VMID" scsi0 "${DISK}G"
    fi
    if [[ ${#QM_SET_ARGS[@]} -gt 0 ]]; then
        qm set "$VMID" "${QM_SET_ARGS[@]}"
    fi
fi

# Cloud-Init DNS defaults are generic; final identity is supplied by this clone.
qm set "$VMID" --nameserver 192.168.0.2 --delete searchdomain

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

# Install a boot-time guest-side check after Cloud-Init has supplied the VM's
# final hostname. QEMU Guest Agent is already used above to read interfaces.
log "Installing Pi-hole hostname registration cron job in VM ${VMID}..."
BASE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CHECKER_PAYLOAD=$(base64 -w0 "$BASE_DIR/homelab-hostname-registration")
DNS_PAYLOAD=$(base64 -w0 "$BASE_DIR/configure-debian-dns.sh")
guest_install="set -e; cloud-init status --wait || true; export DEBIAN_FRONTEND=noninteractive; apt-get update; apt-get install -y cron bind9-dnsutils; printf '%s' '${CHECKER_PAYLOAD}' | base64 -d > /usr/local/sbin/homelab-hostname-registration; chmod 0755 /usr/local/sbin/homelab-hostname-registration; printf '%s\\n' '@reboot root /usr/local/sbin/homelab-hostname-registration' > /etc/cron.d/homelab-hostname-registration; chmod 0644 /etc/cron.d/homelab-hostname-registration; systemctl enable --now cron"
if ((DIRECT_APT)); then
    guest_install="printf '%s\\n' 'Acquire::http::Proxy \"DIRECT\";' 'Acquire::https::Proxy \"DIRECT\";' > /etc/apt/apt.conf.d/99apt-cache-direct; $guest_install"
fi
guest_install="set -e; systemctl disable homelab-dhcp-renew.service 2>/dev/null || true; printf '%s' '$DNS_PAYLOAD' | base64 -d > /usr/local/sbin/homelab-configure-dns; chmod 0755 /usr/local/sbin/homelab-configure-dns; /usr/local/sbin/homelab-configure-dns; $guest_install"
guest_result="$(qm guest exec "$VMID" --synchronous 1 --timeout 0 -- /bin/bash -c "$guest_install" 2>&1)" ||
    fail "Could not install hostname-registration cron job in VM ${VMID}: ${guest_result}"
if jq -e '.exitcode != 0' >/dev/null <<<"$guest_result"; then
    fail "Hostname-registration installation failed in VM ${VMID}: ${guest_result}"
fi
log "Installed hostname-registration check in VM ${VMID}; cron runs at reboot."

# The VM is already booted by the time provisioning installs the cron file.
# Reboot once so cron sees and runs the new @reboot entry.
log "Rebooting VM ${VMID} to run hostname registration at boot."
qm reboot "$VMID" --timeout 120

log "Waiting for VM ${VMID} QEMU Guest Agent after reboot..."
GUEST_AGENT_READY=0
for ((i=1; i<=60; i++)); do
    if qm agent "$VMID" ping >/dev/null 2>&1; then
        GUEST_AGENT_READY=1
        break
    fi
    sleep 2
done
(( GUEST_AGENT_READY == 1 )) ||
    fail "QEMU Guest Agent did not return after rebooting VM ${VMID}."
log "VM ${VMID} rebooted and QEMU Guest Agent is responsive."

log "Source template ${TEMPLATE_ID} preserved."
log "=================================================="

identity=$(qm guest exec "$VMID" --synchronous 1 --timeout 30 -- /bin/sh -c 'cat /etc/machine-id; cat /etc/ssh/ssh_host_ed25519_key.pub')
jq -r '.["out-data"]' <<< "$identity"
VM_CREATED=0
