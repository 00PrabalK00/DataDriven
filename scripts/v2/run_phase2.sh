#!/usr/bin/env bash
# Everything after the CFD batch, run ON THE SERVER, unattended. Waits for the CFD batch to finish, then:
#  1 fit CFD surrogates + switch aero to cfd-v1     2 fast surrogate-environment benchmark (all methods)
#  3 drop server (GPU + CPU pools)                 4 full-simulator benchmark: 8 methods x 10 runs, all parallel
#  5 tail fillers in parallel: encoding comparison (BO in param3/PCA/AE/VAE), 1000-design screen, mass sweep
#  6 studies on the new data (CFD Sobol + surrogates, screen Sobol + surrogates, flight clusters)
#  7 touch RUN_DONE (the laptop watchdog then copies everything back and destroys the instance)
set -uo pipefail
cd /root/DataDriven/python
L=/root/logs
log() { echo "[$(date '+%F %T')] $*" | tee -a $L/phase2.log; }
PY=.venv/bin/python
export MUJOCO_GL=egl OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1

log "waiting for the CFD batch"
while pgrep -f "[c]fd.batch" > /dev/null; do sleep 30; done
log "CFD batch finished: $(grep -c ',True,' ../results/cfd/cfd_results.csv) ok rows"

log "1 fit CFD surrogates"
$PY ../scripts/v2/fit_cfd_map.py > $L/fit.log 2>&1; log "fit rc=$?"; tail -3 $L/fit.log | tee -a $L/phase2.log

log "2 surrogate-environment benchmark"
$PY -m ddd.cli_bench --env surrogate --surrogate-model ../results/cfd/surrogate/descent_model.pkl --noise-sd 0.03 \
  --fail-prob 0.01 --methods random ga sa pso bo tabu gradient moo --runs 10 --budget 200 --parallel 80 \
  --out ../results/benchmark_v2 --tag surrogate_cfd > $L/bench_surrogate.log 2>&1 &
SURR=$!

log "3 drop server"
CHUTESIM_N_GPU=4 CHUTESIM_REMOTE_PER_CONN=100 MUJOCO_EGL_DEVICE_ID=0 setsid nohup $PY -m chutesim.remote serve --port 7777 \
  --workers 150 --gpu-workers 64 --work-root /root/work > $L/drop_server.log 2>&1 < /dev/null &
sleep 20; tail -1 $L/drop_server.log | tee -a $L/phase2.log
export CHUTESIM_REMOTE=127.0.0.1:7777

log "4 full-simulator benchmark (80 runs in parallel)"
$PY -m ddd.cli_bench --env simulator --methods random ga sa pso bo tabu gradient moo --runs 10 --budget 200 \
  --scenarios 5 --fresh-scenarios 20 --parallel 80 --out ../results/benchmark_v2 --tag sim_cfd > $L/bench_sim.log 2>&1 &
SIM=$!

log "5 tail fillers (start now; the drop server shares the cores fairly per connection)"
$PY ../scripts/v2/latent_search.py --runs 3 --budget 50 --scenarios 3 --out results/studies_v2 > $L/latent.log 2>&1 &
LAT=$!
$PY ../scripts/v2/screen_designs.py --n 1000 --scenarios 5 --out results/screen_v2 > $L/screen.log 2>&1 &
SCR=$!
wait $SURR; log "surrogate benchmark rc=$?"
wait $SCR; log "screen rc=$?"
# mass sensitivity on the 30 best + 30 worst screened designs (valid ones)
$PY - <<'E' > $L/tiers.log 2>&1
import csv, json
rows = [r for r in csv.DictReader(open("../results/screen_v2/screen.csv")) if r["status"] == "ok"]
rows.sort(key=lambda r: float(r["score"]))
sel = rows[:30] + rows[len(rows)//2 - 15: len(rows)//2 + 15] + rows[-30:]
json.dump([{"q": float(r["q"]), "slit_len": float(r["slit_len"]), "slit_r": float(r["slit_r"])} for r in sel],
          open("../results/screen_v2/tier_candidates.json", "w"), indent=1)
print(len(rows), "valid screened designs;", len(sel), "tier candidates")
E
for m in 0.085 0.115; do
  $PY ../scripts/v2/screen_designs.py --designs ../results/screen_v2/tier_candidates.json --mass $m --scenarios 5 --out results/screen_v2 > $L/mass_$m.log 2>&1 &
done
wait $LAT; log "latent search rc=$?"
wait $SIM; log "simulator benchmark rc=$?"
wait; log "mass sweep done"

log "6 studies"
$PY -m ddd.cli_studies --what sobol --data ../results/cfd/surrogate/cfd_table.csv --x-cols q,slit_len,slit_r --y-col CdA_m2 --out ../results/studies_v2/cfd_CdA > $L/st1.log 2>&1
$PY -m ddd.cli_studies --what sobol --data ../results/cfd/surrogate/cfd_table.csv --x-cols q,slit_len,slit_r --y-col Cm_alpha_per_deg --out ../results/studies_v2/cfd_Cm > $L/st2.log 2>&1
$PY - <<'E' > $L/st_prep.log 2>&1
import csv
rows = [r for r in csv.DictReader(open("../results/screen_v2/screen.csv")) if r["status"] == "ok"]
with open("../results/screen_v2/screen_valid.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
E
$PY -m ddd.cli_studies --what surrogate --data ../results/screen_v2/screen_valid.csv --x-cols q,slit_len,slit_r --y-col score --out ../results/studies_v2/screen > $L/st3.log 2>&1
$PY -m ddd.cli_studies --what sobol --data ../results/screen_v2/screen_valid.csv --x-cols q,slit_len,slit_r --y-col score --out ../results/studies_v2/screen > $L/st4.log 2>&1
$PY -m ddd.cli_studies --what flight --rebuild-flight --out ../results/studies_v2/flight_sim > $L/st5.log 2>&1
log "studies done"
cp ../config/defaults.json ../results/benchmark_v2/config_used.json
touch /root/DataDriven/RUN_DONE
log "RUN_DONE"
