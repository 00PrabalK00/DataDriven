#!/usr/bin/env bash
# Server run (vast): free-form + cut-out + reference designs, CFD at 0 and 10 deg (level 5, 600 iterations,
# same settings as the v2 batch), plus one time-accurate CFD video; then RUN_DONE for the watchdog.
#   bash scripts/v3/run_free_cfd.sh <jobs> <procs>
set -uo pipefail
cd /root/DataDriven/python
L=/root/logs; PY=.venv/bin/python; OUT=../results/freeform/server
mkdir -p $OUT
log() { echo "[$(date '+%F %T')] $*" | tee -a $L/free_cfd.log; }
export CFD_BACKEND=native OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1
JOBS=${1:-24}; PROCS=${2:-4}
log "start: $(nproc) threads, jobs=$JOBS procs=$PROCS, foam=${CFD_FOAM_VERSION:-2406} decomp=${CFD_DECOMP:-scotch}"
# video first in the background (16 ranks): free03 (star-shaped hole) wake in physical time
( $PY ../scripts/v2/cfd_video.py --name free03_star_hole --design free03 --procs 8 > $L/video.log 2>&1 ; echo "video rc=$?" >> $L/free_cfd.log ) &
VID=$!
$PY -m cfd.batch ../results/freeform/designs_all.json --jobs $JOBS --procs $PROCS --level 5 --iters 600 \
    --ff-workers 32 --csv $OUT/cfd_free.csv > $L/batch.log 2>&1
log "batch rc=$? rows=$(($(wc -l < $OUT/cfd_free.csv) - 1))"
wait $VID
mkdir -p $OUT/video && cp -r ../results/cfd/video/* $OUT/video/ 2>/dev/null; cp ../results/media/v2/cfd_* $OUT/video/ 2>/dev/null
log "RUN_DONE"
touch /root/DataDriven/RUN_DONE
