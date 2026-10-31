#!/bin/sh
set -eu

REPO="/opt/homelab-server-builds"
PROJECT="HomeLab"
RUNDECK_URL="${RD_URL:-http://192.168.0.51:4440}"
API_VERSION="50"

: "${RD_OPTION_GITHUB_TOKEN:?Rundeck GitHub token option is required}"
: "${RD_OPTION_RUNDECK_API_TOKEN:?Rundeck API token option is required}"

cd "$REPO"

askpass=$(mktemp)
workdir=$(mktemp -d)
trap 'rm -f "$askpass"; rm -rf "$workdir"' EXIT HUP INT TERM
cat > "$askpass" <<'EOF'
#!/bin/sh
case "$1" in
  *Username*) printf '%s\n' 'x-access-token' ;;
  *Password*) printf '%s\n' "$RD_OPTION_GITHUB_TOKEN" ;;
  *) exit 1 ;;
esac
EOF
chmod 700 "$askpass"

GIT_ASKPASS="$askpass" GIT_TERMINAL_PROMPT=0 \
  git pull --ff-only origin main

for directory in Rundeck/jobs Rundeck/pipelines; do
  if [ ! -d "$directory" ]; then
    echo "ERROR: Expected managed job directory is missing: $REPO/$directory" >&2
    exit 1
  fi
done

find Rundeck/jobs Rundeck/pipelines -maxdepth 1 -type f -name '*.yaml' -print | sort > "$workdir/job-files"
: > "$workdir/repo-job-ids"

# Import every committed job before deleting anything, so an invalid definition
# cannot leave Rundeck with jobs removed but their replacements not loaded.
while IFS= read -r file; do
  [ -n "$file" ] || continue
  job_id=$(awk '/^[[:space:]]+id:/ { print $2; exit }' "$file" | tr -d "'\"")
  job_uuid=$(awk '/^[[:space:]]+uuid:/ { print $2; exit }' "$file" | tr -d "'\"")
  job_group=$(awk '/^[[:space:]]+group:/ { print $2; exit }' "$file" | tr -d "'\"")
  case "$job_group" in
    jobs|pipelines) ;;
    *) echo "ERROR: $file must assign its job to group 'jobs' or 'pipelines'." >&2; exit 1 ;;
  esac
  if [ -z "$job_id" ] || [ "$job_id" != "$job_uuid" ]; then
    echo "ERROR: $file must have matching id and uuid values." >&2
    exit 1
  fi
  printf '%s\n' "$job_id" >> "$workdir/repo-job-ids"

  response=$(curl --fail-with-body --silent --show-error \
    -X POST "$RUNDECK_URL/api/$API_VERSION/project/$PROJECT/jobs/import?dupeOption=update&jobUuidOption=preserve" \
    -H "X-Rundeck-Auth-Token: $RD_OPTION_RUNDECK_API_TOKEN" \
    -H 'Accept: application/json' \
    -H 'Content-Type: application/yaml' \
    --data-binary "@$file")
  printf '%s' "$response" | python3 -c 'import json,sys; d=json.load(sys.stdin); failed=d.get("failed", []); sys.exit(1 if failed else 0)'
  echo "Imported $job_group job $job_id from $file."
done < "$workdir/job-files"

sort -u "$workdir/repo-job-ids" > "$workdir/repo-job-ids.sorted"

live_jobs=$(curl --fail-with-body --silent --show-error \
  "$RUNDECK_URL/api/$API_VERSION/project/$PROJECT/jobs?max=1000" \
  -H "X-Rundeck-Auth-Token: $RD_OPTION_RUNDECK_API_TOKEN" \
  -H 'Accept: application/json')
printf '%s' "$live_jobs" | python3 -c '
import json, pathlib, sys
jobs=json.load(sys.stdin)
expected=set(pathlib.Path(sys.argv[1]).read_text().splitlines())
for job in jobs:
    if job.get("group") in ("jobs", "pipelines") and job.get("id") not in expected:
        print(job["id"])
' "$workdir/repo-job-ids.sorted" > "$workdir/obsolete-job-ids"

while IFS= read -r job_id; do
  [ -n "$job_id" ] || continue
  curl --fail-with-body --silent --show-error \
    -X DELETE "$RUNDECK_URL/api/$API_VERSION/job/$job_id" \
    -H "X-Rundeck-Auth-Token: $RD_OPTION_RUNDECK_API_TOKEN" \
    -H 'Accept: application/json' >/dev/null
  echo "Removed Rundeck job $job_id because it is absent from Git."
done < "$workdir/obsolete-job-ids"

echo "Rundeck jobs are synchronized with $REPO/Rundeck/jobs and $REPO/Rundeck/pipelines."
