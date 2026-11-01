#!/bin/bash
# Sourced only by the LXC entry points; no VM code depends on this file.
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
log() { printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$*"; }
fail() { log "ERROR: $*" >&2; exit 1; }
uint() {
    if [[ ! $2 =~ ^[1-9][0-9]{0,5}$ ]]; then fail "Invalid $1: $2"; fi
    (( 10#$2 <= $3 )) || fail "Invalid $1: $2"
}
id() { uint ID "$1" 999999; (( $1 >= 100 )) || fail 'IDs must be at least 100'; }
safe_name() { [[ $2 =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$ ]] || fail "Invalid $1: $2"; }
protected() { case "$1" in 110) return 0;; esac; return 1; }
root_and_lock() {
    [[ $EUID == 0 ]] || fail 'Run as root on Proxmox'
    # Never load Ansible configuration from the caller-owned working directory.
    cd -- "$BASE/..";
    for cmd in pct pvesh pvesm jq flock timeout python3; do
        command -v "$cmd" >/dev/null || fail "Missing command: $cmd"
    done
    exec 9>/run/lock/homelab-lxc.lock
    flock -n 9 || fail 'Another LXC operation is running'
}
resources() { pvesh get /cluster/resources --output-format json; }
free_id() {
    id "$1"
    protected "$1" && fail "Protected ID $1"
    local data
    data=$(resources) || fail 'Cannot inspect cluster IDs'
    jq -e --argjson id "$1" 'all(.[]; .vmid != $id)' <<< "$data" >/dev/null || fail "ID $1 already exists"
}
next_id() {
    local value
    value=$(pvesh get /cluster/nextid --output-format json | jq -r '.')
    free_id "$value"
    printf '%s\n' "$value"
}
storage() {
    safe_name storage "$1"
    local data
    data=$(pvesh get "/nodes/$(hostname)/storage" --output-format json)
    jq -e --arg s "$1" --arg c "$2" '.[] | select(.storage == $s and .active == 1) | (.content | split(",") | index($c)) != null' <<< "$data" >/dev/null || fail "Storage $1 must be active and support $2"
}
bridge() {
    safe_name bridge "$1"
    [[ -d /sys/class/net/$1/bridge ]] || fail "Bridge $1 does not exist"
}
network() {
    python3 - "$1" "$2" <<'PY'
import ipaddress, sys
value, gateway = sys.argv[1:]
if value != 'dhcp':
    address = ipaddress.IPv4Interface(value)
    if gateway and ipaddress.IPv4Address(gateway) not in address.network:
        raise SystemExit('Gateway must be in the container subnet')
elif gateway:
    raise SystemExit('DHCP cannot have a static gateway')
PY
}
dns() {
    python3 - "$1" <<'PY'
import ipaddress,sys
values=sys.argv[1].split()
if not values: raise SystemExit('At least one DNS server is required')
for value in values: ipaddress.ip_address(value)
PY
}
not_template() {
    local config
    config=$(pct config "$1") || fail "Container $1 does not exist"
    grep -qx 'template: 1' <<< "$config" && fail "Refusing template $1"
    grep -qx 'protection: 1' <<< "$config" && fail "Container $1 has Proxmox protection"
    return 0
}
wait_ready() {
    local ct=$1 expected=$2 address=''
    for ((i=0;i<90;i++)); do
        address=$(pct exec "$ct" -- ip -4 -o addr show dev eth0 scope global 2>/dev/null | awk 'NR==1 {split($4,a,"/"); print a[1]}' || true)
        if [[ -n $address ]] && pct exec "$ct" -- systemctl is-active --quiet ssh; then break; fi
        sleep 2
    done
    [[ -n $address ]] || fail "Container $ct has no IPv4 address"
    [[ $(pct exec "$ct" -- hostname -s) == "$expected" ]] || fail 'Hostname mismatch'
    pct exec "$ct" -- ip -4 route show default | grep -q '^default ' || fail 'No default IPv4 route'
    pct exec "$ct" -- getent ahostsv4 deb.debian.org >/dev/null || fail 'DNS lookup failed'
    pct exec "$ct" -- /usr/sbin/sshd -t
    # Guest address and arguments are passed as data to the child shell.
    # shellcheck disable=SC2016
    timeout 5 bash -c 'exec 3<>/dev/tcp/$1/22; read -r -t 3 banner <&3; [[ $banner == SSH-* ]]' _ "$address" || fail "SSH not reachable at $address"
    log "Container $ct ready: hostname=$expected IPv4=$address SSH=reachable"
}
