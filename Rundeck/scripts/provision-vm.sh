#!/bin/bash
set -Eeuo pipefail

# Provision a new Debian VM from Proxmox template 9000.
# Run as root on the Proxmox host.

TEMPLATE_ID="${TEMPLATE_ID:-9000}"
VM_CREATED=0

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
Usage: $0 <vm-name> [OPTIONS]

Required Parameters:
  VM name               Name / hostname for the new VM; Proxmox assigns the lowest available VM ID

Optional Parameters:
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
VMID="$(pvesh get /cluster/nextid 2>/dev/null)" ||
    fail "Could not obtain the next available VM ID from Proxmox."
VMID="$(printf '%s' "$VMID" | tr -d '\r\n')"
[[ "$VMID" =~ ^[1-9][0-9]{1,5}$ ]] ||
    fail "Proxmox returned an invalid next VM ID: '${VMID}'."
log "Proxmox selected the lowest available VM ID: ${VMID}."

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
        log "Resizing disk to ${DISK} Gb..."
        qm resize "$VMID" scsi0 "${DISK}G"
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

# Install a boot-time guest-side check after Cloud-Init has supplied the VM's
# final hostname. QEMU Guest Agent is already used above to read interfaces.
log "Installing Pi-hole hostname registration cron job in VM ${VMID}..."
CHECKER_PAYLOAD="$(base64 -w0 <<'CHECKER_SCRIPT'
#!/bin/bash
set -uo pipefail
PATH="/usr/sbin:/usr/bin:/sbin:/bin"
LOG_TAG="homelab-hostname-registration"
LOG_FILE="/var/log/homelab-hostname-registration.log"
DNS_SERVER="192.168.0.2"
log() {
    local message="$*"
    printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$message" >> "$LOG_FILE"
    logger -t "$LOG_TAG" -- "$message" 2>/dev/null || true
}
hostname="$(hostname -s)"
interface=""
current_ip=""
for ((attempt = 1; attempt <= 120; attempt++)); do
    interface="$(ip -4 route show default | awk 'NR == 1 { for (i = 1; i <= NF; i++) if ($i == "dev") { print $(i + 1); exit } }')"
    if [[ -n "$interface" ]]; then
        current_ip="$(ip -4 -o addr show dev "$interface" scope global | awk 'NR == 1 { sub(/\/.*/, "", $4); print $4 }')"
        [[ -n "$current_ip" ]] && break
    fi
    sleep 1
done
if [[ -z "$hostname" || -z "$interface" || -z "$current_ip" ]]; then
    log "ERROR: Hostname, active IPv4 interface, or address unavailable after waiting 120 seconds."
    exit 1
fi
registered_ip="$(dig +time=2 +tries=1 +short A "$hostname" @"$DNS_SERVER" | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ { print; exit }')"
if [[ "$registered_ip" == "$current_ip" ]]; then
    log "SUCCESS: Pi-hole registration for ${hostname} matches ${current_ip}; no DHCP renewal needed."
    exit 0
fi
log "Hostname ${hostname} resolves to '${registered_ip:-<missing>}' at ${DNS_SERVER}; current DHCP address is ${current_ip}. Renewing lease on ${interface}."
if ! dhclient -v "$interface" >> "$LOG_FILE" 2>&1; then
    log "ERROR: DHCP lease renewal failed for ${interface}."
    exit 1
fi
for attempt in 1 2 3 4 5; do
    sleep 5
    current_ip="$(ip -4 -o addr show dev "$interface" scope global | awk 'NR == 1 { sub(/\/.*/, "", $4); print $4 }')"
    registered_ip="$(dig +time=2 +tries=1 +short A "$hostname" @"$DNS_SERVER" | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ { print; exit }')"
    if [[ -n "$current_ip" && "$registered_ip" == "$current_ip" ]]; then
        log "SUCCESS: Pi-hole registration for ${hostname} now matches ${current_ip} after DHCP renewal."
        exit 0
    fi
done
log "ERROR: After DHCP renewal, ${hostname} resolves to '${registered_ip:-<missing>}' while ${interface} has '${current_ip:-<missing>}' (Pi-hole ${DNS_SERVER})."
exit 1
CHECKER_SCRIPT
)"
guest_install="set -e; export DEBIAN_FRONTEND=noninteractive; apt-get update; apt-get install -y cron bind9-dnsutils isc-dhcp-client; printf '%s' '${CHECKER_PAYLOAD}' | base64 -d > /usr/local/sbin/homelab-hostname-registration; chmod 0755 /usr/local/sbin/homelab-hostname-registration; printf '%s\\n' '@reboot root /usr/local/sbin/homelab-hostname-registration; rm -f /usr/local/sbin/homelab-hostname-registration' > /etc/cron.d/homelab-hostname-registration; chmod 0644 /etc/cron.d/homelab-hostname-registration; systemctl enable --now cron"
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

VM_CREATED=0
