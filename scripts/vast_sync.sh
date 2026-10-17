#!/usr/bin/env bash
# Copy remote drop bundles (observation logs + retained frames) back to data/sim_remote every 10 min,
# and do a final sync when vast.ai credit gets low (the instance stops when credit reaches zero).
# Metrics/objectives are already in the local cache (written by the local evaluator); this saves the raw logs.
cd "$(dirname "$0")/.."
VAST=${VAST:-vastai}
OUT=data/sim_remote
LOG=results/benchmark_full/jobs/vast_sync.log
mkdir -p "$OUT"
while :; do
  rsync -az --partial --exclude rgb/ --exclude depth/ --exclude truth/ chute-vast:/root/work/ "$OUT/" 2>>"$LOG" \
    && echo "[$(date '+%F %T')] synced $(du -sh "$OUT" | cut -f1)" >> "$LOG"
  credit=$($VAST show user --raw 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('credit', 99))" 2>/dev/null || echo 99)
  echo "[$(date '+%F %T')] credit \$$credit" >> "$LOG"
  if python3 -c "import sys; sys.exit(0 if float('$credit') < 0.30 else 1)"; then
    rsync -az --partial chute-vast:/root/work/ "$OUT/" 2>>"$LOG"
    rsync -az chute-vast:/root/server.log "$OUT/server.log" 2>>"$LOG"
    echo "[$(date '+%F %T')] LOW CREDIT: final sync done" >> "$LOG"
    sleep 300
  else
    sleep 600
  fi
done
