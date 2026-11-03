#!/usr/bin/env bash
# One machine of the two-machine free-form CFD run. Setup, then its share of the designs, all at once.
#   bash scripts/v3/run_multi.sh <part> <jobs> <procs> [video]
set -uo pipefail
PART=$1; JOBS=$2; PROCS=$3; VIDEO=${4:-}
L=/root/logs; mkdir -p $L /root/DataDriven/results/freeform/server/video
log() { echo "[$(date '+%F %T')] $*" | tee -a $L/multi.log; }
export DEBIAN_FRONTEND=noninteractive
log "setup start"
apt-get update -qq; apt-get install -y -qq curl rsync htop libgl1 libegl1 libosmesa6 libglib2.0-0 > $L/apt.log 2>&1
curl -LsSf https://astral.sh/uv/install.sh | sh > $L/uv.log 2>&1
export PATH=$HOME/.local/bin:$PATH
cd /root/DataDriven/python && uv sync --frozen > $L/sync.log 2>&1
cd .. && bash scripts/v2/install_openfoam_native.sh > $L/of_install.log 2>&1 || { log "OPENFOAM INSTALL FAILED"; exit 1; }
log "setup done"
cd python; PY=.venv/bin/python; OUT=../results/freeform/server
export CFD_BACKEND=native OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1
if [ "$VIDEO" = video ]; then
  ( $PY ../scripts/v2/cfd_video.py --name free03_star_hole --design free03 --alpha 0.001 --procs 24 > $L/video.log 2>&1
    log "video rc=$?"; cp -r ../results/cfd/video/* $OUT/video/ 2>/dev/null; cp ../results/media/v2/cfd_* $OUT/video/ 2>/dev/null ) &
fi
log "batch start: part $PART, $JOBS jobs x $PROCS ranks"
$PY -m cfd.batch ../results/freeform/designs_m$PART.json --jobs $JOBS --procs $PROCS --level 5 --iters 600 \
    --ff-workers 48 --csv $OUT/cfd_m$PART.csv > $L/batch.log 2>&1
log "batch rc=$?"
wait
log "RUN_DONE"; touch /root/DataDriven/RUN_DONE
