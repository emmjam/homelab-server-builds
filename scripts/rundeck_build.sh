
#!/usr/bin/env bash
set -Eeuo pipefail

# Install and start Rundeck Community Edition on Debian.
# Intended for a dedicated Debian 13 VM.
# Safe to rerun; does not configure credentials or a production database.

readonly RUNDECK_REPO_URL="https://packages.rundeck.com/pagerduty/rundeck/any/"
readonly RUNDECK_KEY_URL="https://packages.rundeck.com/pagerduty/rundeck/gpgkey"
readonly KEYRING="/etc/apt/keyrings/rundeck.gpg"
readonly SOURCE_FILE="/etc/apt/sources.list.d/rundeck.list"

log() {
    printf '\n[%s] %s\n' "$(date '+%F %T')" "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

on_error() {
    local rc=$?
    printf '\nERROR: Installation failed at line %s (exit %s).\n' \
        "${BASH_LINENO[0]:-unknown}" "$rc" >&2
    printf 'Check the output above and rerun after resolving the issue.\n' >&2
    exit "$rc"
}
trap on_error ERR

[[ $EUID -eq 0 ]] || die "Run this script as root."
[[ -r /etc/os-release ]] || die "Cannot identify the operating system."

# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == "debian" ]] || die "This script supports Debian only."

if [[ "${VERSION_ID:-}" != "13" ]]; then
    log "WARNING: Designed for Debian 13; detected ${PRETTY_NAME:-unknown}."
fi

for cmd in apt-get systemctl; do
    command -v "$cmd" >/dev/null 2>&1 ||
        die "Required command '$cmd' is missing."
done

log "Installing prerequisites and Java 17 runtime."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates curl gnupg openjdk-21-jre-headless tree

java -version

log "Installing the Rundeck repository signing key."
install -d -m 0755 /etc/apt/keyrings

tmp_key="$(mktemp)"
trap 'rm -f "${tmp_key:-}"' EXIT

curl --fail --silent --show-error --location \
    "$RUNDECK_KEY_URL" -o "$tmp_key"

# Convert the downloaded key to a keyring for apt's signed-by option.
gpg --batch --yes --dearmor --output "$KEYRING" "$tmp_key"
chown root:root "$KEYRING"
chmod 0644 "$KEYRING"
rm -f "$tmp_key"
trap on_error ERR

log "Configuring the official Rundeck Community repository."
printf 'deb [signed-by=%s] %s any main\n' \
    "$KEYRING" "$RUNDECK_REPO_URL" > "$SOURCE_FILE"
chmod 0644 "$SOURCE_FILE"

log "Installing Rundeck Community Edition."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y rundeck

log "Enabling and starting Rundeck."
systemctl enable --now rundeckd
/etc/init.d/rundeckd start
systemctl --no-pager --full status rundeckd

log "Installed package version:"
dpkg-query -W -f='${Package} ${Version}\n' rundeck

printf '\nRundeck installation completed.\n'
IP=$(hostname -I | awk '{print $1}')
printf 'Web interface: http://%s:4440/\n' "$IP"
printf 'Service logs:  /var/log/rundeck/service.log\n'
printf 'If startup is still in progress, inspect the logs before proceeding.\n'

