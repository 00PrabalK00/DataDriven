#!/usr/bin/env bash
# Full benchmark as a queue of (method, run) jobs, each its own MATLAB process (resumable, detached).
# Then merge -> studies -> report. Re-running this script resumes: finished jobs are skipped.
#   parallel MATLAB jobs : results/benchmark_full/jobs/PARALLEL   (re-read before every launch; default 3)
#   remote drops         : config/remote_address  (e.g. 127.0.0.1:7777 via an SSH tunnel; read at each launch)
#   status               : results/benchmark_full/jobs/queue.log, jobs/full_job_<method>_<k>.log
set -o pipefail   # (no -u: empty associative arrays count as unbound in bash)
cd "$(dirname "$0")/.."
D=results/benchmark_full
J=$D/jobs
mkdir -p "$J"
ML=/usr/local/MATLAB/R2026a/bin/matlab
log() { echo "[$(date '+%F %T')] $*" >> "$J/queue.log"; }
# run-index-major order: every method gets run k before any method gets run k+1, so if compute stops
# early all methods have (nearly) the same number of runs; slow sequential methods first within each k
METHODS="bo gradient sa tabu moo pso ga random"
QUEUE=()
for k in $(seq 1 10); do for m in $METHODS; do QUEUE+=("$m:$k"); done; done
done_job() { grep -q "JOB DONE" "$J/full_job_${1}_$(printf %02d "$2").log" 2>/dev/null; }
declare -A PID TRIES
log "queue started (${#QUEUE[@]} jobs)"
if ls $D/full_shard*_runs.mat > /dev/null 2>&1; then
  $ML -batch "run('matlab/scripts/m9_split_shards.m')" >> "$J/queue.log" 2>&1
fi
while :; do
  # reap finished jobs
  for j in "${!PID[@]}"; do
    if ! kill -0 "${PID[$j]}" 2>/dev/null; then
      m=${j%%:*}; k=${j##*:}
      if done_job "$m" "$k"; then log "done $j"; else log "FAILED $j (try ${TRIES[$j]})"; fi
      unset "PID[$j]"
    fi
  done
  pending=0
  par=$(cat "$J/PARALLEL" 2>/dev/null || echo 3)
  for j in "${QUEUE[@]}"; do
    m=${j%%:*}; k=${j##*:}
    done_job "$m" "$k" && continue
    [[ -n "${PID[$j]:-}" ]] && { pending=1; continue; }
    [[ "${TRIES[$j]:-0}" -ge 3 ]] && continue
    pending=1
    [[ ${#PID[@]} -ge $par ]] && continue
    TRIES[$j]=$(( ${TRIES[$j]:-0} + 1 ))
    remote=$(cat config/remote_address 2>/dev/null || true)
    CHUTESIM_REMOTE="$remote" setsid systemd-inhibit --what=sleep:idle --who=parachute-benchmark --why="job $j" \
      $ML -batch "METHOD='$m'; RUNK=$k; run('matlab/scripts/m9_job.m')" \
      >> "$J/full_job_${m}_$(printf %02d "$k").log" 2>&1 < /dev/null &
    PID[$j]=$!
    log "start $j (remote='${remote}', running ${#PID[@]}/$par)"
    sleep 20   # stagger MATLAB start-up
  done
  [[ $pending -eq 0 && ${#PID[@]} -eq 0 ]] && break
  sleep 60
done
log "all jobs finished -> merge"
$ML -batch "run('matlab/scripts/m9_merge.m')" > "$D/merge.log" 2>&1; log "merge exit $?"
CHUTESIM_REMOTE="$(cat config/remote_address 2>/dev/null || true)" \
  $ML -batch "run('matlab/scripts/m10_studies.m')" > results/studies/m10_full.log 2>&1; log "studies exit $?"
python/.venv/bin/python scripts/build_report.py >> "$J/queue.log" 2>&1; log "report exit $?"
