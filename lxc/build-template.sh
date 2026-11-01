#!/bin/bash
set -Eeuo pipefail
BASE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lxc/common.sh
source "$BASE/common.sh"
TEMPLATE_ID=9100
STORAGE=local-zfs
IMAGE_STORAGE=local
BRIDGE=vmbr0
CANDIDATE=''
BACKUP=''
OWNED=0
PROMOTING=0
TEMP=''
usage() { echo "Usage: $0 [--template-id ID] [--storage NAME] [--image-storage NAME] [--bridge NAME] [--inspect]"; }
while (($#)); do
    case $1 in
        --help|-h) usage; exit 0;;
        --inspect)
            (($# == 1)) || fail '--inspect must be used alone'
            root_and_lock
            resources
            pvesh get "/nodes/$(hostname)/storage" --output-format json
            pveam available --section system
            exit 0;;
        --template-id|--storage|--image-storage|--bridge)
            (($# >= 2)) || fail "Missing value for $1"
            case $1 in
                --template-id) TEMPLATE_ID=$2;; --storage) STORAGE=$2;;
                --image-storage) IMAGE_STORAGE=$2;; --bridge) BRIDGE=$2;;
            esac
            shift 2;;
        *) fail "Unknown option $1";;
    esac
done
id "$TEMPLATE_ID"
protected "$TEMPLATE_ID" && fail 'Protected template ID'
root_and_lock
for cmd in pveam ansible-playbook; do command -v "$cmd" >/dev/null || fail "Missing $cmd"; done
storage "$STORAGE" rootdir
storage "$IMAGE_STORAGE" vztmpl
bridge "$BRIDGE"
EXISTING=$(resources)
if jq -e --argjson id "$TEMPLATE_ID" 'any(.[]; .vmid == $id)' <<< "$EXISTING" >/dev/null; then
    CONFIG=$(pct config "$TEMPLATE_ID") || fail 'Target ID belongs to a VM or inaccessible container'
    grep -qx 'template: 1' <<< "$CONFIG" || fail 'Target is not a template'
    grep -Eq '^tags: .*homelab-debian-lxc' <<< "$CONFIG" || fail 'Refusing replacement of an unmanaged template'
fi
cleanup() {
    local rc=$?
    trap - EXIT
    if ((rc != 0)); then
        log 'Template build failed'
        if ((PROMOTING)) && [[ -n $BACKUP ]]; then
            log "Previous working template retained at ID $BACKUP; inspect IDs $TEMPLATE_ID and $BACKUP before retrying"
        else
            log "Previous template $TEMPLATE_ID was not changed"
        fi
    fi
    if ((OWNED)); then
        pct stop "$CANDIDATE" --skiplock 0 >/dev/null 2>&1 || true
        if ! pct destroy "$CANDIDATE" --purge 1; then log "WARNING: clean up owned candidate $CANDIDATE manually"; fi
    fi
    [[ -z $TEMP ]] || rm -rf -- "$TEMP"
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
pveam update
IMAGE=$(pveam available --section system | awk '$2 ~ /^debian-13-standard_.*_amd64\.tar\.(zst|xz|gz)$/ {print $2}' | sort -V | tail -1)
[[ -n $IMAGE ]] || fail 'Official Debian 13 standard image is unavailable'
log "Downloading official Proxmox Debian image $IMAGE"
pveam download "$IMAGE_STORAGE" "$IMAGE"
CANDIDATE=$(next_id)
# Proxmox serializes create; the global lock serializes this project's LXC jobs.
log "Creating temporary build container $CANDIDATE"
pct create "$CANDIDATE" "$IMAGE_STORAGE:vztmpl/$IMAGE" \
    --hostname debian-lxc-build --ostype debian --unprivileged 1 \
    --cores 2 --memory 1024 --swap 0 --rootfs "$STORAGE:4" \
    --net0 "name=eth0,bridge=$BRIDGE,ip=dhcp" --nameserver 192.168.0.2 --onboot 0 \
    --tags homelab-debian-lxc-build
OWNED=1
pct start "$CANDIDATE"
for ((i=0;i<90;i++)); do
    if pct exec "$CANDIDATE" -- getent ahostsv4 deb.debian.org >/dev/null 2>&1; then break; fi
    sleep 2
done
pct exec "$CANDIDATE" -- bash -ec '
    printf "%s\n" '\''Acquire::http::Proxy "http://192.168.0.101:3142";'\'' '\''Acquire::https::Proxy "DIRECT";'\'' > /etc/apt/apt.conf.d/02homelab-proxy
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y python3
'
TEMP=$(mktemp -d)
printf '[lxc]\n%s ansible_connection=pct ansible_python_interpreter=/usr/bin/python3\n' "$CANDIDATE" > "$TEMP/inventory"
export ANSIBLE_CONNECTION_PLUGINS="$BASE/../Ansible/connection_plugins"
export ANSIBLE_ROLES_PATH="$BASE/../Ansible/roles"
export ANSIBLE_LOCAL_TEMP="$TEMP/ansible"
ansible-playbook -i "$TEMP/inventory" "$BASE/../Ansible/playbooks/debian-lxc.yml"
# A second application must make no changes before accepting the baseline.
ANSIBLE_NOCOLOR=1 ansible-playbook -i "$TEMP/inventory" "$BASE/../Ansible/playbooks/debian-lxc.yml" | tee "$TEMP/repeat.log"
grep -Eq 'changed=0[[:space:]]+unreachable=0[[:space:]]+failed=0' "$TEMP/repeat.log" || fail 'Baseline is not idempotent'
wait_ready "$CANDIDATE" debian-lxc-build
pct exec "$CANDIDATE" -- bash -ec '
    . /etc/os-release; test "$ID:$VERSION_ID" = debian:13
    test -z "$(dpkg --audit)"
    apt-get check
    apt-config dump | grep -Fx '\''Acquire::http::Proxy "http://192.168.0.101:3142";'\''
    apt-config dump | grep -Fx '\''Acquire::https::Proxy "DIRECT";'\''
    systemctl is-enabled homelab-lxc-identity.service apt-daily.timer apt-daily-upgrade.timer
    sshd -T | grep -Fx "passwordauthentication no"
    sshd -T | grep -Fx "permitrootlogin without-password"
    locale -a | grep -ix en_GB.utf8
    test "$(readlink /etc/localtime)" = /usr/share/zoneinfo/Europe/London
    apt-get clean
    rm -f /etc/ssh/ssh_host_* /root/.ssh/authorized_keys
    : > /etc/machine-id
    rm -f /var/lib/dbus/machine-id /var/lib/systemd/random-seed
    rm -f /var/lib/dhcp/*.leases /var/lib/dhcp/*.leases~
    rm -rf /var/log/journal/* /tmp/* /var/tmp/*
    find /var/log -type f -exec truncate -s 0 {} +
    rm -f /root/.bash_history
'
pct shutdown "$CANDIDATE" --timeout 60
pct status "$CANDIDATE" | grep -qx 'status: stopped' || fail 'Candidate did not stop cleanly'
pct set "$CANDIDATE" --hostname debian-13-lxc-template --tags homelab-debian-lxc
pct template "$CANDIDATE"
if pct config "$TEMPLATE_ID" >/dev/null 2>&1; then
    BACKUP=$(next_id)
    log "Preserving working template $TEMPLATE_ID at backup ID $BACKUP"
    pct clone "$TEMPLATE_ID" "$BACKUP" --full 1 --hostname "debian-lxc-backup-$BACKUP" --storage "$STORAGE"
    pct template "$BACKUP"
    pct config "$BACKUP" | grep -qx 'template: 1' || fail 'Backup validation failed'
    PROMOTING=1
    pct destroy "$TEMPLATE_ID" --purge 1
else
    free_id "$TEMPLATE_ID"
fi
log "Publishing validated template at ID $TEMPLATE_ID"
pct clone "$CANDIDATE" "$TEMPLATE_ID" --full 1 --hostname debian-13-lxc-template --storage "$STORAGE"
pct template "$TEMPLATE_ID"
pct config "$TEMPLATE_ID" | grep -qx 'template: 1' || fail 'Published target is not a template'
log "SUCCESS: Debian 13 LXC template $TEMPLATE_ID; retained backup=${BACKUP:-none}"
