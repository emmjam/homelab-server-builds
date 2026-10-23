#!/usr/bin/env bash
set -Eeuo pipefail

TEMPLATE_ID=9000

usage() {
    echo "Usage: $0 <new-vmid> <vm-name>" >&2
    exit 2
}

[[ $# -eq 2 ]] || usage

VMID="$1"
NAME="$2"

[[ "$VMID" =~ ^[1-9][0-9]*$ ]] || usage
[[ "$NAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]] || usage

if ! qm config "$TEMPLATE_ID" | grep -qx 'template: 1'; then
    echo "ERROR: VM $TEMPLATE_ID is not a Proxmox template." >&2
    exit 1
fi

if qm status "$VMID" >/dev/null 2>&1; then
    echo "ERROR: VM ID $VMID already exists." >&2
    exit 1
fi

if qm list | awk -v name="$NAME" '$2 == name { found=1 } END { exit !found }'; then
    echo "ERROR: A VM named '$NAME' already exists." >&2
    exit 1
fi

echo "Cloning template $TEMPLATE_ID to VM $VMID ($NAME)..."
qm clone "$TEMPLATE_ID" "$VMID" --name "$NAME" --full 1

echo "Configuring Cloud-Init DHCP..."
qm set "$VMID" --ipconfig0 ip=dhcp
qm cloudinit update "$VMID"

echo "Starting VM $VMID..."
qm start "$VMID"

echo "VM $VMID ($NAME) started."
echo "Check its address with: qm guest cmd $VMID network-get-interfaces"
