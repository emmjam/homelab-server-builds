#!/bin/bash
# Configure only the existing network manager; never replace resolv.conf or bounce a link.
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[[ $EUID == 0 ]] || exit 1
IFACE=$(ip -4 route show default | awk 'NR==1 {for(i=1;i<=NF;i++) if($i=="dev") {print $(i+1); exit}}')
[[ $IFACE =~ ^[a-zA-Z0-9_.-]+$ ]] || { echo 'No valid default-route interface'; exit 1; }
CHANGED=0
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
write_file() {
    local dest=$1 mode=$2
    cat > "$TMP/content"
    if ! cmp -s "$TMP/content" "$dest"; then
        install -D -m "$mode" "$TMP/content" "$dest"
        CHANGED=1
    fi
}
if command -v netplan >/dev/null && networkctl status "$IFACE" --no-pager 2>/dev/null | grep '/run/systemd/network/.*netplan' >/dev/null; then
    MANAGER=netplan-networkd
    write_file /etc/netplan/90-homelab-dns.yaml 0600 <<EOF
network:
  version: 2
  ethernets:
    $IFACE:
      dhcp4: true
      dhcp4-overrides:
        use-dns: false
        use-domains: true
        use-hostname: false
        send-hostname: true
      nameservers:
        addresses: [192.168.0.2]
EOF
    write_file /etc/systemd/resolved.conf.d/90-homelab-dns.conf 0644 <<'EOF'
[Resolve]
DNS=192.168.0.2
LLMNR=no
MulticastDNS=no
EOF
    netplan generate
    # Resolver-only live changes: no netplan apply, link restart or DHCP release.
    resolvectl dns "$IFACE" 192.168.0.2
    resolvectl llmnr "$IFACE" no
    resolvectl mdns "$IFACE" no
elif command -v ifquery >/dev/null && ifquery "$IFACE" >/dev/null 2>&1 && pgrep -a dhclient | grep -qE "(^| )$IFACE( |$)"; then
    MANAGER=ifupdown-dhclient
    [[ -f /etc/dhcp/dhclient.conf ]] || { echo 'No existing dhclient configuration'; exit 1; }
    sed '/^# BEGIN HOMELAB DNS$/,/^# END HOMELAB DNS$/d' /etc/dhcp/dhclient.conf > "$TMP/dhclient"
    cat >> "$TMP/dhclient" <<'EOF'
# BEGIN HOMELAB DNS
send host-name = gethostname();
supersede domain-name-servers 192.168.0.2;
# END HOMELAB DNS
EOF
    write_file /etc/dhcp/dhclient.conf 0644 < "$TMP/dhclient"
    # Proxmox supplies resolv.conf on LXC startup; never edit that generated file.
    grep -Eq '^nameserver[[:space:]]+192\.168\.0\.2([[:space:]]|$)' /etc/resolv.conf || { echo 'Persistent settings staged; resolver update requires managed reboot'; exit 1; }
else
    echo 'Unsupported or ambiguous network manager; no networking changes made'
    exit 1
fi
printf 'DNS_MANAGER=%s DNS_POLICY_CHANGED=%s\n' "$MANAGER" "$CHANGED"
