"""Which free-form designs inflate to a steady shape? Form-find many feasible designs (run on a big machine) and
train an "inflates stably" classifier used as a constraint by the search environment.
Stable = no slack lines and flutter <= 5 mm (the shape solver reaches a steady state).
  python/.venv/bin/python scripts/v3/inflate_scan.py --n 1000 --workers 180
Output (results/freeform/server/inflate/): scan.csv, inflate_clf.pkl, cv.json
"""
import argparse
import csv
import json
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
OUT = ROOT / "results" / "freeform" / "server" / "inflate"


def _one(w):
    from chutesim.config import load_config
    from chutesim.freeform import build_free_geometry, free_design
    from cfd.formfind import form_find
    cfg = load_config(None)
    d = free_design(w, "D6")
    if not build_free_geometry(d, cfg).feasible:
        return None
    try:
        i = form_find(d, cfg).info
    except Exception as e:
        return {"w": list(map(float, w)), "flutter_mm": -1.0, "slack": -1, "stable": 0, "error": str(e)[:80]}
    fl = float(i.get("flutter_amp_m", 0.0)) * 1e3
    return {"w": list(map(float, w)), "flutter_mm": fl, "slack": int(i["slack_lines"]),
            "stable": int(i["slack_lines"] == 0 and fl <= 5.0), "error": ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000, help="candidate designs (only feasible ones are form-found)")
    ap.add_argument("--workers", type=int, default=180)
    a = ap.parse_args()
    from scipy.stats import qmc
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_predict
    from chutesim.freeform import n_weights
    OUT.mkdir(parents=True, exist_ok=True)
    k = n_weights("D6")
    W = qmc.scale(qmc.LatinHypercube(d=k, seed=23).random(a.n), -1.6 * np.ones(k), 1.6 * np.ones(k))
    rows = []
    with ProcessPoolExecutor(a.workers) as ex, open(OUT / "scan.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["flutter_mm", "slack", "stable", "error"] + [f"w{i}" for i in range(k)])
        for j, r in enumerate(ex.map(_one, W, chunksize=1)):
            if r:
                rows.append(r)
                w.writerow([r["flutter_mm"], r["slack"], r["stable"], r["error"]] + r["w"])
                f.flush()
            if j % 100 == 0:
                print(j, len(rows), flush=True)
    X = np.array([r["w"] for r in rows])
    y = np.array([r["stable"] for r in rows])
    clf = RandomForestClassifier(500, min_samples_leaf=2, class_weight="balanced", random_state=0, n_jobs=-1)
    p = cross_val_predict(clf, X, y, cv=5, method="predict_proba")[:, 1]
    tp = ((p > .5) & (y == 1)).sum()
    cv = {"n": len(y), "stable_frac": float(y.mean()), "accuracy": float(((p > .5) == y).mean()),
          "precision_stable": float(tp / max((p > .5).sum(), 1)), "recall_stable": float(tp / max(y.sum(), 1))}
    (OUT / "cv.json").write_text(json.dumps(cv, indent=1))
    clf.fit(X, y)
    clf.n_jobs = 1   # one call per search request, many searches in parallel
    pickle.dump(clf, open(OUT / "inflate_clf.pkl", "wb"))
    print(cv)


if __name__ == "__main__":
    main()
