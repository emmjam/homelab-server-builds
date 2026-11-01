#!/bin/bash
set -Eeuo pipefail
BASE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=Rundeck/scripts/common.sh
source "$BASE/common.sh"
TEMPLATE_ID=9001 STORAGE=local-zfs IMAGE_STORAGE=local BRIDGE=vmbr0
CANDIDATE='' BACKUP='' BUILD_TOKEN=''
OWNED=0 PROMOTING=0
STATE_FILE=/run/homelab-lxc-build.state
MODE=${1:-}
usage() {
    echo "Usage: $0 --prepare [--template-id ID] [--storage NAME] [--image-storage NAME] [--bridge NAME]"
    echo "       $0 --complete ID | --abort ID | --ansible-exec ID BASE64_COMMAND | --inspect"
    echo 'Rundeck runs Ansible between prepare and complete; no Ansible runtime is required on TNAS.'
}
load_build() {
    [[ -f $STATE_FILE ]] || fail 'No active LXC template build'
    # This state is created by root under /run, never in the writable checkout.
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    [[ $CANDIDATE == "$1" ]] || fail 'Candidate does not match the active build'
    local config
    config=$(pct config "$CANDIDATE") || fail 'Active build container is missing'
    grep -Fq "$BUILD_TOKEN" <<< "$config" || fail 'Build ownership tag does not match'
}
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
        pct stop "$CANDIDATE" >/dev/null 2>&1 || true
        if pct destroy "$CANDIDATE" --purge 1; then
            rm -f -- "$STATE_FILE"
        else
            log "WARNING: clean up owned candidate $CANDIDATE manually; build state retained"
        fi
    fi
    exit "$rc"
}
case $MODE in
    --inspect-service-vm)
        (($# == 2)) || fail 'Expected service VM ID'
        case $2 in 112|113) :;; *) fail 'Not a relocated service VM';; esac
        [[ $EUID == 0 ]] || fail 'Run as root'
        qm config "$2" | grep -E '^(name|agent|net[0-9]+|ipconfig[0-9]+):'
        qm agent "$2" ping
        qm guest exec "$2" --timeout 15 -- systemctl --no-pager --plain list-units --type=service --all
        exit 0;;
    --migrate-template-ids)
        (($# == 1)) || fail 'Use --migrate-template-ids alone'
        root_and_lock
        free_id 9001
        free_id 9998
        CONFIG=$(pct config 9100) || fail 'Original template 9100 is missing'
        grep -qx 'template: 1' <<< "$CONFIG" || fail 'Source is not a template'
        grep -Eq '^tags: .*homelab-debian-lxc' <<< "$CONFIG" || fail 'Source is unmanaged'
        ! grep -qx 'protection: 1' <<< "$CONFIG" || fail 'Source is protected'
        pct clone 9100 9001 --full 1 --hostname debian-lxc-template --storage local-zfs
        pct template 9001
        pct config 9001 | grep -qx 'template: 1' || fail 'New template validation failed'
        pct clone 9100 9998 --full 1 --hostname debian-lxc-template-backup --storage local-zfs
        pct template 9998
        pct config 9998 | grep -qx 'template: 1' || fail 'New backup validation failed'
        pct destroy 9100 --purge 1
        log 'SUCCESS: debian-lxc-template=9001 debian-lxc-template-backup=9998'
        exit 0;;
    --delete-obsolete-backup)
        (($# == 3)) || fail 'Expected backup ID and DELETE-ID confirmation'
        id "$2"
        [[ $3 == "DELETE-$2" ]] || fail 'Incorrect backup deletion confirmation'
        root_and_lock
        CONFIG=$(pct config "$2") || fail 'Backup not found'
        grep -qx "hostname: debian-lxc-backup-$2" <<< "$CONFIG" || fail 'Not an obsolete LXC backup'
        grep -qx 'template: 1' <<< "$CONFIG" || fail 'Backup must be a template'
        grep -Eq '^tags: .*homelab-debian-lxc' <<< "$CONFIG" || fail 'Unmanaged backup'
        ! grep -qx 'protection: 1' <<< "$CONFIG" || fail 'Protected backup'
        pct status "$2" | grep -qx 'status: stopped' || fail 'Backup is not stopped'
        pct destroy "$2" --purge 1
        free_id "$2"
        log "SUCCESS: obsolete LXC backup $2 deleted"
        exit 0;;
    --help|-h) usage; exit 0;;
    --inspect)
        (($# == 1)) || fail '--inspect must be used alone'
        root_and_lock
        resources
        pvesh get "/nodes/$(hostname)/storage" --output-format json
        pveam available --section system
        exit 0;;
    --ansible-exec)
        (($# == 3)) || fail 'Expected candidate ID and encoded guest command'
        id "$2"
        root_and_lock
        load_build "$2"
        COMMAND=$(printf '%s' "$3" | base64 -d) || fail 'Invalid command encoding'
        # Only the active, ownership-tagged temporary build guest is accessible.
        pct exec "$CANDIDATE" -- /bin/sh -c "$COMMAND"
        exit $?;;
    --complete|--abort)
        (($# == 2)) || fail 'Expected candidate ID'
        id "$2"
        root_and_lock
        load_build "$2"
        OWNED=1
        trap cleanup EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
        if [[ $MODE == --abort ]]; then log "Aborting owned build container $CANDIDATE"; exit 0; fi;;
    --prepare)
        shift
        while (($#)); do
            (($# >= 2)) || fail "Missing value for $1"
            case $1 in
                --template-id) TEMPLATE_ID=$2;; --storage) STORAGE=$2;;
                --image-storage) IMAGE_STORAGE=$2;; --bridge) BRIDGE=$2;;
                *) fail "Unknown option $1";;
            esac
            shift 2
        done
        id "$TEMPLATE_ID"
        protected "$TEMPLATE_ID" && fail 'Protected template ID'
        root_and_lock
        [[ ! -e $STATE_FILE ]] || fail 'A previous build is active; inspect it before retrying'
        command -v pveam >/dev/null || fail 'Missing pveam'
        storage "$STORAGE" rootdir
        storage "$IMAGE_STORAGE" vztmpl
        bridge "$BRIDGE"
        EXISTING=$(resources)
        if jq -e --argjson id "$TEMPLATE_ID" 'any(.[]; .vmid == $id)' <<< "$EXISTING" >/dev/null; then
            CONFIG=$(pct config "$TEMPLATE_ID") || fail 'Target ID belongs to a VM or inaccessible container'
            grep -qx 'template: 1' <<< "$CONFIG" || fail 'Target is not a template'
            grep -Eq '^tags: .*homelab-debian-lxc' <<< "$CONFIG" || fail 'Refusing replacement of an unmanaged template'
        fi
        BUILD_TOKEN="build-$(cat /proc/sys/kernel/random/uuid)"
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
            --tags "homelab-debian-lxc-build;$BUILD_TOKEN"
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
        umask 077
        printf 'CANDIDATE=%q\nTEMPLATE_ID=%q\nSTORAGE=%q\nBUILD_TOKEN=%q\n' \
            "$CANDIDATE" "$TEMPLATE_ID" "$STORAGE" "$BUILD_TOKEN" > "$STATE_FILE"
        log 'Candidate prepared; Rundeck will now apply the Ansible baseline'
        printf 'LXC_CANDIDATE_ID=%s\n' "$CANDIDATE"
        OWNED=0
        exit 0;;
    *) usage; fail 'Choose an explicit build phase';;
esac
wait_ready "$CANDIDATE" debian-lxc-build
# The quoted script runs inside the guest.
# shellcheck disable=SC2016
pct exec "$CANDIDATE" -- bash -ec '
    . /etc/os-release; test "$ID:$VERSION_ID" = debian:13
    test -z "$(dpkg --audit)"
    apt-get check
    apt-config dump | grep -Fx '\''Acquire::http::Proxy "http://192.168.0.101:3142";'\''
    apt-config dump | grep -Fx '\''Acquire::https::Proxy "DIRECT";'\''
    systemctl is-enabled homelab-lxc-identity.service apt-daily.timer apt-daily-upgrade.timer
    sshd -T | grep -Fx "passwordauthentication no"
    sshd -T | grep -Fx "permitrootlogin no"
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
    rm -rf /root/.ansible /root/.cache
'
pct shutdown "$CANDIDATE" --timeout 60
pct status "$CANDIDATE" | grep -qx 'status: stopped' || fail 'Candidate did not stop cleanly'
pct set "$CANDIDATE" --hostname debian-lxc-template --tags homelab-debian-lxc
pct template "$CANDIDATE"
if pct config "$TEMPLATE_ID" >/dev/null 2>&1; then
    BACKUP=9998
    if pct config "$BACKUP" >/dev/null 2>&1; then
        BACKUP_CONFIG=$(pct config "$BACKUP")
        grep -qx 'hostname: debian-lxc-template-backup' <<< "$BACKUP_CONFIG" || fail 'Backup ID 9998 is occupied by another guest'
        grep -qx 'template: 1' <<< "$BACKUP_CONFIG" || fail 'Backup ID is not a template'
        grep -Eq '^tags: .*homelab-debian-lxc' <<< "$BACKUP_CONFIG" || fail 'Backup ID is unmanaged'
        ! grep -qx 'protection: 1' <<< "$BACKUP_CONFIG" || fail 'Backup is protected'
        pct status "$BACKUP" | grep -qx 'status: stopped' || fail 'Backup is not stopped'
        pct destroy "$BACKUP" --purge 1
    else
        free_id "$BACKUP"
    fi
    log "Preserving working template $TEMPLATE_ID at backup ID $BACKUP"
    pct clone "$TEMPLATE_ID" "$BACKUP" --full 1 --hostname debian-lxc-template-backup --storage "$STORAGE"
    pct template "$BACKUP"
    pct config "$BACKUP" | grep -qx 'template: 1' || fail 'Backup validation failed'
    PROMOTING=1
    pct destroy "$TEMPLATE_ID" --purge 1
else
    free_id "$TEMPLATE_ID"
fi
log "Publishing validated template at ID $TEMPLATE_ID"
pct clone "$CANDIDATE" "$TEMPLATE_ID" --full 1 --hostname debian-lxc-template --storage "$STORAGE"
pct template "$TEMPLATE_ID"
pct config "$TEMPLATE_ID" | grep -qx 'template: 1' || fail 'Published target is not a template'
log "SUCCESS: Debian 13 LXC template $TEMPLATE_ID; retained backup=${BACKUP:-none}"
