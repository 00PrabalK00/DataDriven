#!/usr/bin/env bash
# Launch the full benchmark as detached, resumable shards (survive the terminal/session closing).
# Re-running this script resumes: completed (method, run) pairs are skipped, cached drops are reused.
# Progress: results/benchmark_full/full_shard*_progress.json
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results/benchmark_full
for s in ${SHARDS:-1 2 3}; do
  # systemd-inhibit keeps the laptop from auto-suspending while a shard runs
  setsid nohup systemd-inhibit --what=sleep:idle --who=parachute-benchmark --why="benchmark shard $s" \
    /usr/local/MATLAB/R2026a/bin/matlab -batch "SHARD=$s; run('matlab/scripts/m9_full_shard.m')" \
    > results/benchmark_full/shard$s.log 2>&1 < /dev/null &
  echo "shard $s pid $!"
done
