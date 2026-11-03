#!/usr/bin/env bash
# Laptop-side watchdog for several vast instances (ssh aliases chute-a, chute-b): copies results back every 3 min.
# Destroys all instances after a final copy on: results/v3_destroy_now (user decision), credit < MIN_CREDIT, or
# MAX_HOURS. RUN_DONE only logs: the user decides what happens to a finished machine.
#   scripts/v3/vast_watchdog_multi.sh "<id_a> <id_b>" [max_hours=3] [min_credit=0.3]
set -uo pipefail
IDS=$1; MAX_H=${2:-3}; MIN_CREDIT=${3:-0.3}
cd "$(dirname "$0")/../.."
VAST=${VAST:-vastai}; LOG=results/v3_watchdog.log
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
T0=$(date +%s)
sync_back() {
  for h in chute-a chute-b; do
    mkdir -p results/freeform/server_$h data/v3_server/$h
    timeout 170 rsync -az --partial $h:/root/DataDriven/results/freeform/server/ results/freeform/server_$h/ 2>>"$LOG"
    timeout 170 rsync -az --partial --ignore-existing $h:/root/DataDriven/results/cfd/logs/ results/cfd/logs/ 2>>"$LOG"
    timeout 170 rsync -az --partial --ignore-existing $h:/root/DataDriven/results/cfd/shapes/ results/cfd/shapes/ 2>>"$LOG"
    timeout 60 rsync -az --partial $h:/root/logs/ data/v3_server/$h/ 2>>"$LOG"
  done
}
destroy() {
  log "final sync before destroy ($1)"; sync_back; sync_back
  for id in $IDS; do log "destroying $id"; $VAST destroy instance "$id" -y >> "$LOG" 2>&1; done
  sleep 20; log "instances listed after destroy: $($VAST show instances --raw 2>/dev/null | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  exit 0
}
log "multi watchdog started for $IDS (max ${MAX_H} h, min credit \$${MIN_CREDIT})"
while :; do
  sleep 180
  sync_back && log "synced"
  credit=$($VAST show user --raw 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('credit', 99))" 2>/dev/null || echo 99)
  hrs=$(( ($(date +%s) - T0) / 3600 )); log "credit \$$credit, elapsed ${hrs} h"
  if [ -e results/v3_destroy_now ]; then rm -f results/v3_destroy_now; destroy "user request"; fi
  if python3 -c "import sys; sys.exit(0 if float('$credit') < float('$MIN_CREDIT') else 1)"; then destroy "credit below \$$MIN_CREDIT"; fi
  if [ "$hrs" -ge "$MAX_H" ]; then destroy "time limit ${MAX_H} h"; fi
done
