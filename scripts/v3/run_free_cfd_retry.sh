#!/usr/bin/env bash
# Takes over the tail of run_free_cfd.sh: wait for the running batch + video, then rerun failed cases with the
# potentialFoam fallback (cfd.case.run_stl), copy the video, RUN_DONE.
#   bash scripts/v3/run_free_cfd_retry.sh <jobs> <procs> <pid>...
set -uo pipefail
cd /root/DataDriven/python
L=/root/logs; PY=.venv/bin/python; OUT=../results/freeform/server
log() { echo "[$(date '+%F %T')] $*" | tee -a $L/free_cfd.log; }
export CFD_BACKEND=native OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1
JOBS=$1; PROCS=$2; shift 2
log "retry controller: waiting for $*"
for p in "$@"; do while kill -0 "$p" 2>/dev/null; do sleep 30; done; done
log "first pass done: rows=$(($(wc -l < $OUT/cfd_free.csv) - 1)), failed=$(grep -c ',False,' $OUT/cfd_free.csv)"
$PY -m cfd.batch ../results/freeform/designs_all.json --jobs $JOBS --procs $PROCS --level 5 --iters 600 \
    --ff-workers 32 --csv $OUT/cfd_free.csv > $L/batch_retry.log 2>&1
log "retry pass rc=$?: $(grep -c ' a=' $L/batch_retry.log) cases rerun"
mkdir -p $OUT/video && cp -r ../results/cfd/video/* $OUT/video/ 2>/dev/null; cp ../results/media/v2/cfd_* $OUT/video/ 2>/dev/null
log "RUN_DONE"
touch /root/DataDriven/RUN_DONE
