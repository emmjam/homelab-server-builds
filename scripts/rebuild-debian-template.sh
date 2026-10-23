
#!/usr/bin/env bash
set -Eeuo pipefail

# TNAS Debian 13 template rebuild
# Approved template: 9000
# Temporary candidate: 9002
#
# Promotion policy:
#   All tests pass -> delete 9000, clone candidate as 9000, make it a template.
#   Any pre-promotion failure -> delete candidate and preserve 9000.
#
# Run as root on TNAS.

TEMPLATE_ID=9000
CANDIDATE_ID=9002
TEMPLATE_NAME=debian-13-template
CANDIDATE_NAME=debian-13-template-candidate
REPO_DIR=/root/homelab-server-builds
BASELINE="$REPO_DIR/scripts/debian-baseline.sh"
LOG=/var/log/debian-template-rebuild.log
APT_PROXY=http://192.168.0.101:3142

exec > >(tee -a "$LOG") 2>&1

CANDIDATE_CREATED=0
PROMOTION_STARTED=0

die() {
    echo "ERROR: $*" >&2
    exit 1
}

cleanup() {
    rc=$?
    if [[ "$rc" -ne 0 && "$CANDIDATE_CREATED" -eq 1 &&
          "$PROMOTION_STARTED" -eq 0 ]]; then
        echo "Build or tests failed. Removing candidate $CANDIDATE_ID."
        qm stop "$CANDIDATE_ID" --skiplock 1 >/dev/null 2>&1 || true
        qm destroy "$CANDIDATE_ID" --purge 1 >/dev/null 2>&1 || true
        echo "Existing template $TEMPLATE_ID has not been changed."
    elif [[ "$rc" -ne 0 && "$PROMOTION_STARTED" -eq 1 ]]; then
        echo "ERROR during promotion. Do not delete candidate $CANDIDATE_ID;"
        echo "it may be needed to complete recovery of template $TEMPLATE_ID."
    fi
    echo "Finished with exit code $rc at $(date -Is)"
}
trap cleanup EXIT

echo "=== Debian template rebuild started: $(date -Is) ==="

[[ "$EUID" -eq 0 ]] || die "Run this script as root."
command -v qm >/dev/null || die "Proxmox qm command not found."
command -v git >/dev/null || die "git not found."
command -v base64 >/dev/null || die "base64 not found."
command -v python3 >/dev/null || die "python3 not found."

# Refresh the committed baseline if the repository is checked out on TNAS.
if [[ -d "$REPO_DIR/.git" ]]; then
    git -C "$REPO_DIR" fetch origin main
    git -C "$REPO_DIR" checkout main
    git -C "$REPO_DIR" pull --ff-only origin main
fi

[[ -s "$BASELINE" ]] ||
    die "Baseline not found at $BASELINE. Put the committed debian-baseline.sh there."

qm status "$TEMPLATE_ID" >/dev/null 2>&1 ||
    die "Approved template $TEMPLATE_ID does not exist."

qm config "$TEMPLATE_ID" | grep -q '^template: 1$' ||
    die "VM $TEMPLATE_ID is not a Proxmox template."

if qm status "$CANDIDATE_ID" >/dev/null 2>&1; then
    die "VM ID $CANDIDATE_ID already exists. Resolve it before rebuilding."
fi

echo "Cloning approved template $TEMPLATE_ID to candidate $CANDIDATE_ID."
qm clone "$TEMPLATE_ID" "$CANDIDATE_ID" \
    --full 1 \
    --name "$CANDIDATE_NAME"
CANDIDATE_CREATED=1

qm set "$CANDIDATE_ID" --ipconfig0 ip=dhcp
qm cloudinit update "$CANDIDATE_ID"
qm start "$CANDIDATE_ID"

echo "Waiting for the guest agent."
agent_ready=0
for _ in $(seq 1 60); do
    if qm guest cmd "$CANDIDATE_ID" ping >/dev/null 2>&1; then
        agent_ready=1
        break
    fi
    sleep 5
done
[[ "$agent_ready" -eq 1 ]] || die "Guest agent did not become ready."

# Run a command in the guest and return its exit status.
guest_run() {
    local command="$1"
    local result pid status exited code
    result=$(qm guest exec "$CANDIDATE_ID" --timeout 30 -- \
        /bin/sh -c "$command")
    pid=$(printf '%s' "$result" |
        python3 -c 'import json,sys; print(json.load(sys.stdin)["pid"])')

    while :; do
        status=$(qm guest exec-status "$CANDIDATE_ID" "$pid")
        exited=$(printf '%s' "$status" |
            python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("exited",False)).lower())')
        if [[ "$exited" == true ]]; then
            code=$(printf '%s' "$status" |
                python3 -c 'import json,sys; print(json.load(sys.stdin).get("exitcode",1))')
            printf '%s' "$status" |
                python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("out-data",""),end=""); print(d.get("err-data",""),file=sys.stderr,end="")'
            [[ "$code" == 0 ]]
            return
        fi
        sleep 2
    done
}

# Transfer and execute the exact baseline script.
echo "Transferring baseline to candidate."
PAYLOAD=$(base64 -w0 "$BASELINE")
guest_run "printf '%s' '$PAYLOAD' | base64 -d > /root/debian-baseline.sh && chmod 700 /root/debian-baseline.sh && /root/debian-baseline.sh" ||
    die "Baseline execution failed."

# Validation checks.
check() {
    local description="$1"
    local command="$2"
    echo "TEST: $description"
    guest_run "$command" || die "Test failed: $description"
}

check "qemu-guest-agent active" \
    "systemctl is-active --quiet qemu-guest-agent"

check "fail2ban active" \
    "systemctl is-active --quiet fail2ban"

check "SSH password authentication disabled" \
    "! /usr/sbin/sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication) yes$'"

check "SSH root login disabled" \
    "! /usr/sbin/sshd -T | grep '^permitrootlogin yes$'"

check "SSH public-key authentication enabled" \
    "/usr/sbin/sshd -T | grep -q '^pubkeyauthentication yes$'"

check "apt-cacher-ng proxy configured" \
    "grep -Fx 'Acquire::http::Proxy \"$APT_PROXY\";' /etc/apt/apt.conf.d/02proxy"

check "en_GB.UTF-8 locale available" \
    "locale -a | grep -qi '^en_GB\\.utf8$'"

check "/usr/sbin included in PATH" \
    "printf '%s' \"\$PATH\" | tr ':' '\\n' | grep -Fxq /usr/sbin"

echo "All validation tests passed."

# Shut down candidate before converting it to a template.
echo "Shutting down candidate."
qm shutdown "$CANDIDATE_ID" --timeout 120

stopped=0
for _ in $(seq 1 60); do
    if qm status "$CANDIDATE_ID" | grep -q 'status: stopped'; then
        stopped=1
        break
    fi
    sleep 2
done
[[ "$stopped" -eq 1 ]] ||
    die "Candidate did not stop cleanly; existing template preserved."

# All tests passed: execute the requested replacement.
PROMOTION_STARTED=1
echo "All tests passed. Deleting old template $TEMPLATE_ID."
qm destroy "$TEMPLATE_ID" --purge 1

echo "Cloning tested candidate $CANDIDATE_ID as replacement $TEMPLATE_ID."
qm clone "$CANDIDATE_ID" "$TEMPLATE_ID" \
    --full 1 \
    --name "$TEMPLATE_NAME"

echo "Converting replacement to template."
qm template "$TEMPLATE_ID"

qm config "$TEMPLATE_ID" | grep -q '^template: 1$' ||
    die "Replacement VM exists but template verification failed."

echo "Removing temporary candidate."
qm destroy "$CANDIDATE_ID" --purge 1
CANDIDATE_CREATED=0

echo "SUCCESS: template $TEMPLATE_ID replaced and verified."
echo "=== Rebuild completed: $(date -Is) ==="

