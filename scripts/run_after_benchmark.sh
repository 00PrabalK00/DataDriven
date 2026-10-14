#!/usr/bin/env bash
# Detached follow-up chain (resumable, idempotent):
#   1. when shard 1 (random/ga/pso) finishes -> start shard 4 (multi-objective)
#   2. when shards 1-4 are all finished      -> merge results (m9_merge)
#   3. then run the studies on benchmark data (m10: surrogates, Sobol, k-means/PCA, latent search)
#   4. then build the report (scripts/build_report.py)
# A shard is "finished" when its log contains the final summary table (line with "best_median").
set -uo pipefail
cd "$(dirname "$0")/.."
D=results/benchmark_full
ML=/usr/local/MATLAB/R2026a/bin/matlab
done_shard() { [ -f "$D/shard$1.log" ] && grep -q "best_median" "$D/shard$1.log"; }
running_shard() { pgrep -f "SHARD=$1; run" > /dev/null; }
log() { echo "[$(date '+%F %T')] $*" >> "$D/chain.log"; }
log "chain started"
until done_shard 1; do sleep 120; done
if ! done_shard 4 && ! running_shard 4; then
  log "shard 1 done -> starting shard 4 (moo)"
  SHARDS=4 scripts/run_full_benchmark.sh >> "$D/chain.log" 2>&1
fi
until done_shard 1 && done_shard 2 && done_shard 3 && done_shard 4; do sleep 120; done
log "all shards done -> merge"
systemd-inhibit --what=sleep:idle --who=parachute-benchmark --why="merge+studies" \
  $ML -batch "run('matlab/scripts/m9_merge.m')" > "$D/merge.log" 2>&1
log "merge exit $?"
systemd-inhibit --what=sleep:idle --who=parachute-benchmark --why="studies" \
  $ML -batch "run('matlab/scripts/m10_studies.m')" > results/studies/m10_full.log 2>&1
log "studies exit $?"
python/.venv/bin/python scripts/build_report.py >> "$D/chain.log" 2>&1
log "report exit $?"
