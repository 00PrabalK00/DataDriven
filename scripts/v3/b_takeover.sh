#!/usr/bin/env bash
# Machine B: when its own batch ends, run machine A's designs too (A is about 3x slower per case).
#   bash scripts/v3/b_takeover.sh <own_batch_pid> <jobs> <procs>
set -uo pipefail
cd /root/DataDriven/python
L=/root/logs; OUT=../results/freeform/server
export CFD_BACKEND=native OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1
while kill -0 "$1" 2>/dev/null; do sleep 10; done
echo "[$(date '+%F %T')] takeover: running part 0 on B" >> $L/multi.log
.venv/bin/python -m cfd.batch ../results/freeform/designs_m0.json --jobs $2 --procs $3 --level 5 --iters 600 \
    --ff-workers 48 --csv $OUT/cfd_m0_on_b.csv > $L/batch_takeover.log 2>&1
echo "[$(date '+%F %T')] takeover rc=$?" >> $L/multi.log
touch /root/DataDriven/TAKEOVER_DONE
