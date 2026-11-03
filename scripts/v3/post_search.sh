#!/usr/bin/env bash
# After the free-form CFD, on the fast machine: merge CFD results, drop shapes without a steady inflated shape, fit
# surrogates, run all methods on the free-form surrogate environment. Everything lands in results/freeform/server/.
set -uo pipefail
cd /root/DataDriven/python
L=/root/logs; PY=.venv/bin/python; R=../results/freeform; S=$R/server
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1
log() { echo "[$(date '+%F %T')] $*" | tee -a $L/post.log; }
mkdir -p $S/analysis $S/bench; ln -sfn server/analysis $R/analysis
log "merge"
$PY - <<'P' 2>&1 | tee -a $L/post.log
import csv, glob
rows, seen = [], set()
for f in ["../results/freeform/checkpoint_cfd_free.csv", "../results/freeform/pilot_cfd.csv"] + sorted(glob.glob("../results/freeform/server/cfd_m*.csv")):
    for r in csv.DictReader(open(f)):
        k = (r["name"], r["alpha_deg"])
        if r["ok"] == "True" and k not in seen:
            seen.add(k); rows.append(r)
keys = list(rows[0].keys())
with open("../results/freeform/merged_cfd.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
print(len(rows), "ok runs merged")
P
$PY ../scripts/v3/shape_health.py > $R/health_b.csv 2>/dev/null
$PY - <<'P' 2>&1 | tee -a $L/post.log
d = {}
for f in ("../results/freeform/shape_health_local.csv", "../results/freeform/health_b.csv"):
    for l in open(f):
        if l.count(",") == 7 and not l.startswith(("name,", "?")):
            d[l.split(",")[0]] = l.strip()
open("../results/freeform/shape_health.csv", "w").write("name,flutter_mm,slack_lines,flipped_frac,proj_cm2,span_cm,min_line_N,converged\n" + "\n".join(d.values()) + "\n")
print(len(d), "designs with health data")
P
log "analysis"
$PY ../scripts/v3/free_analysis.py --clf $S/inflate/inflate_clf.pkl 2>&1 | grep -v -i warn | tee -a $L/post.log
log "benchmark"
$PY -m ddd.cli_bench --env free --surrogate-model $S/analysis/free_model.pkl --noise-sd 0.03 --fail-prob 0.01 \
    --runs 10 --budget 200 --parallel 80 --out $S/bench --tag free --no-resume 2>&1 | tail -12 | tee -a $L/post.log
log "POST_DONE"; touch /root/DataDriven/POST_DONE
