#!/usr/bin/env bash
set +x
set -Eeuo pipefail

RUNDECK_URL="${RD_URL:-http://192.168.0.51:4440}"
API_VERSION="50"
TOKEN=$(python3 /opt/homelab-server-builds/Rundeck/scripts/read-secret.py RUNDECK_TOKEN)
ACTION="${RD_OPTION_ACTION:-}"
VMNAME="${RD_OPTION_VMNAME:-}"
CORES="${RD_OPTION_CORES:-}"
MEMORY="${RD_OPTION_MEMORY:-}"
DISK="${RD_OPTION_DISK:-}"
TARGET="${RD_OPTION_TARGET:-}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ -n "$TOKEN" ]] || fail 'RUNDECK_TOKEN is missing from /tmp/secrets.txt.'
case "$ACTION" in
  create)
    [[ "$VMNAME" =~ ^[a-zA-Z0-9]([a-zA-Z0-9._-]{0,61}[a-zA-Z0-9])?$ ]] || fail 'Provide a valid VM hostname.'
    [[ "$CORES" =~ ^[1-9][0-9]*$ ]] || fail 'CPU cores must be a positive integer.'
    [[ "$MEMORY" =~ ^[1-9][0-9]*$ ]] || fail 'Memory in GB must be a positive integer.'
    [[ "$DISK" =~ ^[1-9][0-9]*$ ]] || fail 'Disk size in GB must be a positive integer.'
    ;;
  delete)
    [[ "$TARGET" =~ ^([1-9][0-9]{0,5}|[a-zA-Z0-9]([a-zA-Z0-9._-]{0,61}[a-zA-Z0-9])?)$ ]] || fail 'Provide a valid exact VM name or numeric VM ID.'
    ;;
  *) fail 'Action must be create or delete.' ;;
esac

api() {
  curl --fail-with-body --silent --show-error "$@" \
    -H "X-Rundeck-Auth-Token: $TOKEN" \
    -H 'Accept: application/json'
}

run_child() {
  local label="$1" job_id="$2" payload="$3" response execution_id status attempt output
  printf 'Starting child job: %s (%s)\n' "$label" "$job_id"
  response=$(api -X POST "$RUNDECK_URL/api/$API_VERSION/job/$job_id/run" \
    -H 'Content-Type: application/json' -d "$payload") || fail "Could not start child job: $label"
  execution_id=$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id", ""))')
  [[ "$execution_id" =~ ^[0-9]+$ ]] || fail "Rundeck did not return an execution ID for $label."
  printf 'Child execution %s started for %s.\n' "$execution_id" "$label"

  for attempt in $(seq 1 720); do
    response=$(api "$RUNDECK_URL/api/$API_VERSION/execution/$execution_id") || fail "Could not check child execution $execution_id."
    status=$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", "unknown"))')
    case "$status" in
      succeeded) break ;;
      failed|aborted|timedout|other) ;;
      *) sleep 5; continue ;;
    esac
    output=$(api "$RUNDECK_URL/api/$API_VERSION/execution/$execution_id/output?format=text" || true)
    printf '%s\n' "$output" >&2
    fail "$label ended with status $status (execution $execution_id)."
  done
  [[ "$status" == succeeded ]] || fail "$label did not finish within one hour (execution $execution_id)."
  output=$(api "$RUNDECK_URL/api/$API_VERSION/execution/$execution_id/output?format=text" || true)
  printf '%s\n' "$output"
  printf 'Child job succeeded: %s (execution %s).\n' "$label" "$execution_id"
}

empty_payload='{}'
if [[ "$ACTION" == create ]]; then
  run_child 'HomeLab - Update GitHub Checkout' '310dfa4f-e27f-4945-be6a-7380ef75e586' "$empty_payload"
  run_child 'HomeLab - Deploy Build Scripts to TNAS' '51192072-1984-48dd-9fe8-88d78c339b31' "$empty_payload"
  payload=$(VMNAME="$VMNAME" CORES="$CORES" MEMORY="$MEMORY" DISK="$DISK" python3 -c 'import json,os; print(json.dumps({"options":{"vmname":os.environ["VMNAME"],"cores":os.environ["CORES"],"memory":os.environ["MEMORY"],"disk":os.environ["DISK"]}}))')
  run_child 'Proxmox - Clone VM' '5c7a2428-7407-43cd-90ff-886e5f5447dd' "$payload"
else
  payload=$(TARGET="$TARGET" python3 -c 'import json,os; print(json.dumps({"options":{"target":os.environ["TARGET"]}}))')
  run_child 'Proxmox - Delete VM' '4eb507e0-9514-4cf2-babc-347df5faf73c' "$payload"
fi
