#!/usr/bin/env bash
# Replaces run_phase3b.sh: one client connection can have at most CHUTESIM_REMOTE_PER_CONN (60) drops in flight, so a
# single sequential screen/verify client leaves most of the 214 server workers idle once the mini benchmark ends.
# Split the 400-design screen into 4 parallel parts and the remaining verify designs into 2, each batch = 60 drops,
# merge the parts, wait for the mini benchmark, then studies + RUN_DONE.
#   bash scripts/v2/run_phase3c.sh <mini_benchmark_pid>
set -uo pipefail
cd /root/DataDriven/python
L=/root/logs; PY=.venv/bin/python
log() { echo "[$(date '+%F %T')] $*" | tee -a $L/phase2.log; }
export MUJOCO_GL=egl OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1 CHUTESIM_REMOTE=127.0.0.1:7777
export CHUTESIM_REMOTE_BATCH_TIMEOUT=21600
log "P3c: screen in 4 parallel parts, verify in 2; waiting for mini benchmark: $*"
$PY - <<'P' > $L/p3c_prep.log 2>&1
import csv, json
from chutesim.config import load_config
from ddd import doe
cfg = load_config(None)
res = doe.lhs_designs(n=400, seed=7, baselines=(), cfg=cfg)
D = res[0] if isinstance(res, tuple) else res
D = [list(map(float, d)) for d in (D["designs"] if isinstance(D, dict) else D)]
for k in range(4):
    json.dump([{"q": d[0], "slit_len": d[1], "slit_r": d[2]} for d in D[k::4]], open(f"../results/screen_v2/part{k}.json", "w"))
W = json.load(open("../results/benchmark_v2/surrogate_winners.json"))
done = sum(1 for _ in open("../results/benchmark_v2/verify_winners.csv")) - 1
rest = W[max(done, 0):]
for k in range(2):
    json.dump(rest[k::2], open(f"../results/benchmark_v2/verify_part{k}.json", "w"))
print(len(D), done, len(rest))
P
P=()
for k in 0 1 2 3; do
  $PY ../scripts/v2/screen_designs.py --designs ../results/screen_v2/part$k.json --scenarios 3 --batch 20 --tag screen_part$k --out results/screen_v2 > $L/screen_p$k.log 2>&1 &
  P+=($!)
done
for k in 0 1; do
  $PY ../scripts/v2/screen_designs.py --designs ../results/benchmark_v2/verify_part$k.json --scenarios 10 --fresh --tag verify_winners_part$k --batch 6 --out results/benchmark_v2 > $L/verify_p$k.log 2>&1 &
  P+=($!)
done
for p in "${P[@]}"; do wait $p; done
log "screen + verify parts done"
$PY - <<'P' >> $L/p3c_prep.log 2>&1
import csv, glob
def merge(parts, out, keep_existing=False):
    rows = list(csv.DictReader(open(out))) if keep_existing else []
    for p in parts:
        rows += list(csv.DictReader(open(p)))
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(out, len(rows))
merge(sorted(glob.glob("../results/screen_v2/screen_part*.csv")), "../results/screen_v2/screen.csv")
# verify parts were split by interleaving; row order does not matter (each row carries its design)
merge(sorted(glob.glob("../results/benchmark_v2/verify_winners_part*.csv")), "../results/benchmark_v2/verify_winners.csv", keep_existing=True)
P
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
