#!/bin/bash
set -Eeuo pipefail
BASE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=Rundeck/scripts/common.sh
source "$BASE/common.sh"
CTID=''
CONFIRM=''
while (($#)); do
    case $1 in
        --help|-h) echo "Usage: $0 --id ID --confirm DELETE-ID"; exit 0;;
        --id|--confirm)
            (($# >= 2)) || fail "Missing value for $1"
            case $1 in --id) CTID=$2;; --confirm) CONFIRM=$2;; esac
            shift 2;;
        *) fail "Unknown option $1";;
    esac
done
id "$CTID"
[[ $CONFIRM == "DELETE-$CTID" ]] || fail "Confirmation must be exactly DELETE-$CTID"
protected "$CTID" && fail "Protected infrastructure container $CTID"
root_and_lock
not_template "$CTID"
STATUS=$(pct status "$CTID")
case $STATUS in
    'status: running')
        log "Shutting down container $CTID cleanly"
        pct shutdown "$CTID" --timeout 60 || fail 'Shutdown failed; container was not deleted';;
    'status: stopped') :;;
    *) fail "Unexpected container status: $STATUS";;
esac
pct status "$CTID" | grep -qx 'status: stopped' || fail 'Container did not stop; refusing deletion'
# Recheck protection immediately before destruction.
not_template "$CTID"
log "Deleting container $CTID"
pct destroy "$CTID" --purge 1
DATA=$(resources) || fail 'Cannot verify deletion'
jq -e --argjson id "$CTID" 'all(.[]; .vmid != $id)' <<< "$DATA" >/dev/null || fail 'Container still exists after deletion'
log "SUCCESS: container $CTID deleted"
