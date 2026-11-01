#!/bin/bash
set -Eeuo pipefail
BASE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lxc/common.sh
source "$BASE/common.sh"
CTID='' HOSTNAME='' CORES='' MEMORY='' DISK='' STORAGE='' BRIDGE='' IP='' GATEWAY='' DNS='' SEARCH_DOMAIN='' TEMPLATE_ID='' SSH_PUBLIC_KEY=''
CREATED=0
TEMP=''
usage() {
    echo "Usage: $0 --id ID --hostname NAME --cores N --memory GB --disk GB --storage NAME --bridge NAME --ip dhcp|IPv4/CIDR --dns 'IP [IP ...]' --template-id ID [--gateway IPv4] [--search-domain DOMAIN] [--ssh-public-key 'TYPE BASE64 COMMENT']"
}
while (($#)); do
    case $1 in
        --help|-h) usage; exit 0;;
        --id|--hostname|--cores|--memory|--disk|--storage|--bridge|--ip|--gateway|--dns|--search-domain|--template-id|--ssh-public-key)
            (($# >= 2)) || fail "Missing value for $1"
            case $1 in
                --id) CTID=$2;; --hostname) HOSTNAME=$2;; --cores) CORES=$2;;
                --memory) MEMORY=$2;; --disk) DISK=$2;; --storage) STORAGE=$2;;
                --bridge) BRIDGE=$2;; --ip) IP=$2;; --gateway) GATEWAY=$2;;
                --dns) DNS=$2;; --search-domain) SEARCH_DOMAIN=$2;;
                --template-id) TEMPLATE_ID=$2;; --ssh-public-key) SSH_PUBLIC_KEY=$2;;
            esac
            shift 2;;
        *) fail "Unknown option $1";;
    esac
done
id "$CTID"; id "$TEMPLATE_ID"
[[ $CTID != "$TEMPLATE_ID" ]] || fail 'Container ID must differ from template ID'
protected "$CTID" && fail "Protected infrastructure ID $CTID"
[[ $HOSTNAME =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]] || fail 'Invalid hostname (use a single DNS label)'
uint cores "$CORES" 256
uint memory "$MEMORY" 1024
uint disk "$DISK" 262144
safe_name storage "$STORAGE"; safe_name bridge "$BRIDGE"
[[ -n $IP ]] || fail 'Missing --ip'
network "$IP" "$GATEWAY"
dns "$DNS"
if [[ -n $SEARCH_DOMAIN ]]; then
    [[ $SEARCH_DOMAIN =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$ ]] || fail 'Invalid DNS search domain'
fi
root_and_lock
free_id "$CTID"
storage "$STORAGE" rootdir
bridge "$BRIDGE"
CONFIG=$(pct config "$TEMPLATE_ID") || fail 'Cannot read source template'
grep -qx 'template: 1' <<< "$CONFIG" || fail 'Source must be an LXC template'
grep -Eq '^tags: .*homelab-debian-lxc' <<< "$CONFIG" || fail 'Source must have the Debian LXC baseline tag'
DATA=$(resources)
jq -e --arg name "$HOSTNAME" 'all(.[]; .name != $name)' <<< "$DATA" >/dev/null || fail 'Hostname already exists in cluster'
SOURCE_GB=$(python3 - "$CONFIG" <<'PY'
import re,sys,math
m=re.search(r'^rootfs: .*\bsize=([0-9.]+)([KMGT])(?:,|$)',sys.argv[1],re.M)
if not m: raise SystemExit('Cannot determine template root disk size')
print(math.ceil(float(m[1])*{'K':1/1024**2,'M':1/1024,'G':1,'T':1024}[m[2]]))
PY
)
((DISK >= SOURCE_GB)) || fail "Disk cannot be smaller than template ($SOURCE_GB GB)"
cleanup() {
    local rc=$?
    trap - EXIT
    if ((rc != 0 && CREATED)); then
        log "Cleaning this run's incomplete container $CTID"
        pct stop "$CTID" >/dev/null 2>&1 || true
        pct destroy "$CTID" --purge 1 || log "WARNING: cleanup failed; inspect container $CTID"
    fi
    [[ -z $TEMP ]] || rm -rf -- "$TEMP"
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [[ -n $SSH_PUBLIC_KEY ]]; then
    [[ $SSH_PUBLIC_KEY != *$'\n'* && $SSH_PUBLIC_KEY =~ ^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521))[[:space:]]+[A-Za-z0-9+/]+=*([[:space:]].*)?$ ]] || fail 'Expected one OpenSSH public key without options'
    TEMP=$(mktemp -d)
    printf '%s\n' "$SSH_PUBLIC_KEY" > "$TEMP/authorized_keys"
    ssh-keygen -lf "$TEMP/authorized_keys" >/dev/null || fail 'Invalid SSH public key'
fi
MAC=''
for ((i=0;i<10;i++)); do
    MAC="02:$(od -An -N5 -tx1 /dev/urandom | tr -s ' ' ':' | sed 's/^://;s/:$//')"
    # Check local node configurations too, rather than relying only on randomness.
    if ! grep -riFq -- "$MAC" /etc/pve/nodes/*/lxc/*.conf /etc/pve/nodes/*/qemu-server/*.conf 2>/dev/null; then break; fi
    MAC=''
done
[[ -n $MAC ]] || fail 'Could not allocate a unique MAC address'
NET="name=eth0,bridge=$BRIDGE,hwaddr=$MAC,ip=$IP"
[[ -z $GATEWAY ]] || NET+=",gw=$GATEWAY"
log "Cloning LXC template $TEMPLATE_ID to $CTID ($HOSTNAME)"
# Proxmox clone handles its own incomplete clone rollback. We never destroy an
# unknown target if clone fails, since an external administrator may own it.
pct clone "$TEMPLATE_ID" "$CTID" --full 1 --hostname "$HOSTNAME" --storage "$STORAGE"
CREATED=1
ARGS=(--hostname "$HOSTNAME" --cores "$CORES" --memory "$((MEMORY * 1024))" --swap 0 --net0 "$NET" --nameserver "$DNS" --onboot 1 --tags homelab-lxc)
[[ -z $SEARCH_DOMAIN ]] || ARGS+=(--searchdomain "$SEARCH_DOMAIN")
pct set "$CTID" "${ARGS[@]}"
if ((DISK > SOURCE_GB)); then pct resize "$CTID" rootfs "${DISK}G"; fi
pct start "$CTID"
if [[ -n $SSH_PUBLIC_KEY ]]; then
    pct exec "$CTID" -- install -d -m 0700 /root/.ssh
    pct push "$CTID" "$TEMP/authorized_keys" /root/.ssh/authorized_keys --perms 0600 --user 0 --group 0
fi
wait_ready "$CTID" "$HOSTNAME"
if [[ $IP != dhcp ]]; then
    ACTUAL=$(pct exec "$CTID" -- ip -4 -o addr show dev eth0 scope global)
    grep -Fq " ${IP} " <<< "$ACTUAL" || fail 'Static IPv4 configuration did not take effect'
fi
ACTUAL_CONFIG=$(pct config "$CTID")
grep -qx "cores: $CORES" <<< "$ACTUAL_CONFIG" || fail 'CPU configuration mismatch'
grep -qx "memory: $((MEMORY * 1024))" <<< "$ACTUAL_CONFIG" || fail 'Memory configuration mismatch'
grep -Eq "^rootfs: .*size=${DISK}G(,|$)" <<< "$ACTUAL_CONFIG" || fail 'Disk configuration mismatch'
# Guest health and identity checks fail the operation rather than reporting success early.
# Quoted script executes inside the container.
# shellcheck disable=SC2016
pct exec "$CTID" -- bash -ec '
    . /etc/os-release; test "$ID:$VERSION_ID" = debian:13
    test -s /etc/machine-id
    test -s /etc/ssh/ssh_host_ed25519_key
    test -z "$(dpkg --audit)"
    apt-config dump | grep -Fx '\''Acquire::http::Proxy "http://192.168.0.101:3142";'\''
    apt-config dump | grep -Fx '\''Acquire::https::Proxy "DIRECT";'\''
'
CREATED=0
log "SUCCESS: container=$CTID hostname=$HOSTNAME cores=$CORES memory=${MEMORY}GB disk=${DISK}GB MAC=$MAC template=$TEMPLATE_ID"
