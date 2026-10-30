#!/usr/bin/env bash
# Laptop-side watchdog for a rented vast.ai instance: copies results back every 10 min and DESTROYS the
# instance when (a) the server writes /root/DataDriven/RUN_DONE, (b) MAX_HOURS have passed, or (c) credit
# drops below MIN_CREDIT. Destruction always happens after a final full copy. Nothing is left running.
#   scripts/v2/vast_watchdog.sh <instance_id> [max_hours=8] [min_credit=2]
set -uo pipefail
ID=$1; MAX_H=${2:-8}; MIN_CREDIT=${3:-2}
cd "$(dirname "$0")/../.."
VAST=${VAST:-vastai}
LOG=results/v2_watchdog.log
mkdir -p results data/v2_server
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
T0=$(date +%s)
sync_back() {   # results + raw observation logs (frames are only kept for the retained sample)
  rsync -az --partial chute-vast:/root/DataDriven/results/ results/ 2>>"$LOG"
  rsync -az --partial chute-vast:/root/DataDriven/data/cache/ data/cache/ 2>>"$LOG"
  rsync -az --partial --exclude rgb/ --exclude depth/ --exclude truth/ chute-vast:/root/work/ data/v2_server/work/ 2>>"$LOG"
  rsync -az --partial chute-vast:/root/logs/ data/v2_server/logs/ 2>>"$LOG"
}
destroy() {
  log "final sync before destroy ($1)"
  sync_back; sync_back
  rsync -az --partial chute-vast:/root/work/ data/v2_server/work/ 2>>"$LOG"   # retained full bundles too
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
  sleep 600
  sync_back && log "synced"
  credit=$($VAST show user --raw 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('credit', 99))" 2>/dev/null || echo 99)
  hrs=$(( ($(date +%s) - T0) / 3600 ))
  log "credit \$$credit, elapsed ${hrs} h"
  if ssh -o ConnectTimeout=20 chute-vast 'test -f /root/DataDriven/RUN_DONE' 2>/dev/null; then destroy "all runs done"; fi
  if python3 -c "import sys; sys.exit(0 if float('$credit') < $MIN_CREDIT else 1)"; then destroy "credit below \$$MIN_CREDIT"; fi
  if [ "$hrs" -ge "$MAX_H" ]; then destroy "time cap ${MAX_H} h reached"; fi
done
