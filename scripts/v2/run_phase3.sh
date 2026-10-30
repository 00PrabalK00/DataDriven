#!/usr/bin/env bash
# Budget-reduced phase 3 (see results/v2_notes.md): verify the surrogate-benchmark winners in the full simulator,
# a mini full-simulator benchmark of all methods, a 400-design screen for the real-drop tiers, the encoding
# comparison, studies, RUN_DONE. Uses the drop server already running on 127.0.0.1:7777.
set -uo pipefail
cd /root/DataDriven/python
L=/root/logs; PY=.venv/bin/python
log() { echo "[$(date '+%F %T')] $*" | tee -a $L/phase2.log; }
export MUJOCO_GL=egl OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1 CHUTESIM_REMOTE=127.0.0.1:7777
log "P3 start: verify winners + mini benchmark + screen + latent (parallel)"
$PY - <<'P' > $L/verify_prep.log 2>&1
import json, glob
D = [json.load(open(f)) for f in sorted(glob.glob("../results/benchmark_v2/surrogate_cfd_runs/*.json"))]
json.dump([{"q": r["xbest"][0], "slit_len": r["xbest"][1], "slit_r": r["xbest"][2], "method": r["method"], "run": r.get("runIndex", r.get("run"))} for r in D],
          open("../results/benchmark_v2/surrogate_winners.json", "w"), indent=1)
print(len(D))
P
$PY ../scripts/v2/screen_designs.py --designs ../results/benchmark_v2/surrogate_winners.json --scenarios 10 --fresh --tag verify_winners --batch 80 --out results/benchmark_v2 > $L/verify.log 2>&1 &
V=$!
$PY -m ddd.cli_bench --env simulator --methods random ga sa pso bo tabu gradient moo --runs 3 --budget 60 \
  --scenarios 3 --fresh-scenarios 10 --parallel 24 --out ../results/benchmark_v2 --tag sim_cfd_mini > $L/bench_sim_mini.log 2>&1 &
B=$!
$PY ../scripts/v2/screen_designs.py --n 400 --scenarios 3 --batch 50 --out results/screen_v2 > $L/screen.log 2>&1 &
S=$!
$PY ../scripts/v2/latent_search.py --runs 2 --budget 40 --scenarios 3 --out results/studies_v2 > $L/latent.log 2>&1 &
T=$!
wait $V; log "verify winners rc=$?"
wait $S; log "screen rc=$?"
wait $T; log "latent rc=$?"
wait $B; log "mini benchmark rc=$?"
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
