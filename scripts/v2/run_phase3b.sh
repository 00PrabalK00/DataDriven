#!/usr/bin/env bash
# Takes over the tail of run_phase3.sh: the original screen client kept timing out (45 min batch timeout vs ~90 min
# queue wait under full load) and resending its whole batch. Restart the screen with small batches and a long
# timeout (same for the verify job), wait for the still-running mini benchmark (orphaned from phase 3), then studies + RUN_DONE.
set -uo pipefail
cd /root/DataDriven/python
L=/root/logs; PY=.venv/bin/python
log() { echo "[$(date '+%F %T')] $*" | tee -a $L/phase2.log; }
export MUJOCO_GL=egl OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1 CHUTESIM_REMOTE=127.0.0.1:7777
export CHUTESIM_REMOTE_BATCH_TIMEOUT=21600
log "P3b: verify + screen restarted (batch 10, timeout 6 h); waiting for mini benchmark: $*"
$PY ../scripts/v2/screen_designs.py --designs ../results/benchmark_v2/surrogate_winners.json --scenarios 10 --fresh --tag verify_winners --batch 4 --out results/benchmark_v2 > $L/verify2.log 2>&1 &
V=$!
$PY ../scripts/v2/screen_designs.py --n 400 --scenarios 3 --batch 10 --out results/screen_v2 > $L/screen2.log 2>&1
log "screen rc=$?"
wait $V; log "verify winners rc=$?"
for p in "$@"; do while kill -0 "$p" 2>/dev/null; do sleep 30; done; done
log "mini benchmark finished"
log "studies"
$PY -m ddd.cli_studies --what sobol --data ../results/cfd/surrogate/cfd_table.csv --x-cols q,slit_len,slit_r --y-col CdA_m2 --out ../results/studies_v2/cfd_CdA > $L/st1.log 2>&1
$PY -m ddd.cli_studies --what sobol --data ../results/cfd/surrogate/cfd_table.csv --x-cols q,slit_len,slit_r --y-col Cm_alpha_per_deg --out ../results/studies_v2/cfd_Cm > $L/st2.log 2>&1
$PY - <<'P' > $L/st_prep.log 2>&1
import csv
rows = [r for r in csv.DictReader(open("../results/screen_v2/screen.csv")) if r["status"] == "ok"]
with open("../results/screen_v2/screen_valid.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(len(rows))
P
$PY -m ddd.cli_studies --what surrogate --data ../results/screen_v2/screen_valid.csv --x-cols q,slit_len,slit_r --y-col score --out ../results/studies_v2/screen > $L/st3.log 2>&1
$PY -m ddd.cli_studies --what sobol --data ../results/screen_v2/screen_valid.csv --x-cols q,slit_len,slit_r --y-col score --out ../results/studies_v2/screen > $L/st4.log 2>&1
$PY -m ddd.cli_studies --what flight --rebuild-flight --out ../results/studies_v2/flight_sim > $L/st5.log 2>&1
log "studies done"
cp ../config/defaults.json ../results/benchmark_v2/config_used.json
touch /root/DataDriven/RUN_DONE
log "RUN_DONE"
