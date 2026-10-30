#!/usr/bin/env bash
# Laptop-side watchdog for the free-form CFD run on vast: copies results back every 5 min and DESTROYS the
# instance when (a) results/v3_destroy_now exists (user decision), (b) MAX_HOURS have passed, or (c) credit
# drops below MIN_CREDIT. Destruction always happens after a final full copy.
# Only server-side outputs are pulled, so nothing local is overwritten: results/freeform/ (server CSV,
# designs, logs) in full; results/cfd/shapes and results/cfd/logs with --ignore-existing.
#   scripts/v3/vast_watchdog_cfd.sh <instance_id> [max_hours=6] [min_credit=0.15]
set -uo pipefail
ID=$1; MAX_H=${2:-6}; MIN_CREDIT=${3:-0.15}
cd "$(dirname "$0")/../.."
VAST=${VAST:-vastai}
LOG=results/v3_watchdog.log
mkdir -p results/freeform/server data/v3_server
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
T0=$(date +%s)
sync_back() {
  rsync -az --partial chute-vast:/root/DataDriven/results/freeform/server/ results/freeform/server/ 2>>"$LOG"
  rsync -az --partial --ignore-existing chute-vast:/root/DataDriven/results/cfd/shapes/ results/cfd/shapes/ 2>>"$LOG"
  rsync -az --partial --ignore-existing chute-vast:/root/DataDriven/results/cfd/logs/ results/cfd/logs/ 2>>"$LOG"
  rsync -az --partial chute-vast:/root/logs/ data/v3_server/logs/ 2>>"$LOG"
}
destroy() {
  log "final sync before destroy ($1)"
  sync_back; sync_back
  log "destroying instance $ID"
  $VAST destroy instance "$ID" -y >> "$LOG" 2>&1 || $VAST destroy instance "$ID" >> "$LOG" 2>&1
  sleep 20
  if $VAST show instances --raw 2>/dev/null | python3 -c "import json,sys; sys.exit(0 if any(str(x['id'])=='$ID' for x in json.load(sys.stdin)) else 1)"; then
    log "WARNING: instance $ID still listed after destroy; retrying"; $VAST destroy instance "$ID" -y >> "$LOG" 2>&1
  else
    log "instance $ID destroyed"
  fi
  exit 0
}
log "watchdog started for instance $ID (max ${MAX_H} h, min credit \$${MIN_CREDIT})"
while :; do
  sleep 300
  sync_back && log "synced"
  credit=$($VAST show user --raw 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('credit', 99))" 2>/dev/null || echo 99)
  hrs=$(( ($(date +%s) - T0) / 3600 ))
  log "credit \$$credit, elapsed ${hrs} h"
  # RUN_DONE does not destroy: the user decides (more work may follow). Destroy on request: touch results/v3_destroy_now
  if timeout 60 ssh -o ConnectTimeout=20 chute-vast test -e /root/DataDriven/RUN_DONE 2>/dev/null; then log "RUN_DONE seen: holding instance for the user's decision"; fi
  if [ -e results/v3_destroy_now ]; then rm -f results/v3_destroy_now; destroy "user request"; fi
  if python3 -c "import sys; sys.exit(0 if float('$credit') < float('$MIN_CREDIT') else 1)"; then destroy "credit below \$$MIN_CREDIT"; fi
  if [ "$hrs" -ge "$MAX_H" ]; then destroy "time limit ${MAX_H} h"; fi
done
