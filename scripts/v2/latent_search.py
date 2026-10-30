"""Encoding comparison (week 2-3 + 12): the same search method (BO) and budget in four design representations:
param3 (q, slit length, slit radius), PCA, autoencoder and VAE latent spaces of free-form outlines (+ slit knobs),
scored by the full simulator + sensors + shared pipeline (drop server via CHUTESIM_REMOTE).

  python scripts/v2/latent_search.py --runs 3 --budget 50 --scenarios 3 --out results/studies_v2
Writes latent_search.csv (one row per run) and latent_best_designs.json (best design per run).
"""
import argparse
import csv
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


class DesignListEnv:
    """Env over lists of chutesim designs (compact lists or radial dicts), same result format as ddd.envs."""

    def __init__(self, seeds, tag):
        self.seeds, self.tag, self._ev = seeds, tag, None

    def __call__(self, designs):
        from chutesim.config import load_config
        from chutesim.evaluate import Evaluator
        from ddd.envs import _result
        if self._ev is None:
            self._ev = Evaluator(load_config(), n_workers=2)
        res = self._ev.evaluate(designs, self.seeds, tag=self.tag)
        n = len(res)
        score, sec, speed = np.zeros(n), np.zeros(n), np.full(n, np.nan)
        status, drops, hits = np.empty(n, dtype=object), np.zeros(n), np.zeros(n)
        for i, r in enumerate(res):
            o = r["objective"]
            score[i], status[i] = o["score"], str(o["status"])
            drops[i], hits[i] = r["simulated_drops"], r["cache_hits"]
            lat = o.get("mean_lateral_speed")
            sec[i] = lat if lat is not None else o["P_infeasible"]
            if o.get("mean_preimpact_vz") is not None:
                speed[i] = o["mean_preimpact_vz"]
        return _result(score, sec, status, drops, hits, speed)


def one_run(args):
    rep_name, run, budget, n_scen = args
    from chutesim.config import load_config
    from ddd import rep
    from ddd.latent import latent_env, make_representations
    from ddd.methods import run_method
    md = ROOT / "results/studies_v2/models"
    m = rep.load_models(md)
    R = np.load(md / "shapes.npz")["R"]
    reps = make_representations(R, m["pca"], m["ae"].get(4), m["vae"], k=4, cfg=load_config())
    r = reps[rep_name]
    base = load_config()["objective"]["search_seed_base"]
    env = latent_env(r, DesignListEnv(list(range(base, base + n_scen)), f"latent-{rep_name}"))
    out = run_method("bo", env, budget=budget, seed=500 + run, bounds=(r.lb, r.ub))
    best = r.decode_one(out["xbest"])
    return {"representation": rep_name, "run": run, "best_score": float(out["fbest"]),
            "valid_geometry_rate": float(out["validGeometryRate"]), "sensing_failure_rate": float(out["sensingFailureRate"]),
            "requests": int(out["requests"]), "simulated_drops": int(out["simulatedDrops"]), "best_design": best,
            "trace": [float(v) for v in out["bestTrace"]]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--budget", type=int, default=50)
    ap.add_argument("--scenarios", type=int, default=3)
    ap.add_argument("--reps", default="param3,pca,autoencoder,vae")
    ap.add_argument("--out", default="results/studies_v2")
    a = ap.parse_args()
    jobs = [(r, k, a.budget, a.scenarios) for r in a.reps.split(",") for k in range(1, a.runs + 1)]
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(len(jobs)) as ex:
        res = list(ex.map(one_run, jobs))
    with open(out / "latent_search.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["representation", "run", "best_score", "valid_geometry_rate", "sensing_failure_rate", "requests", "simulated_drops"])
        for r in res:
            w.writerow([r[k] for k in ("representation", "run", "best_score", "valid_geometry_rate", "sensing_failure_rate", "requests", "simulated_drops")])
    (out / "latent_best_designs.json").write_text(json.dumps(res, indent=1))
    for r in res:
        print(r["representation"], r["run"], round(r["best_score"], 4), "valid", r["valid_geometry_rate"])


if __name__ == "__main__":
    main()
