"""Free-form CFD study analysis (after the vast batch): table, surrogates (course wk 6), Sobol (wk 2), the
free-form surrogate model for the optimiser benchmark, figures.
  python/.venv/bin/python scripts/v3/free_analysis.py [--csv results/freeform/server/cfd_free.csv]
Writes results/freeform/analysis/: free_table.csv, surrogate_cv.json, free_model.pkl, sobol.json, figures.
"""
import argparse
import csv
import json
import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
OUT = ROOT / "results" / "freeform" / "analysis"


def load(csv_path):
    rows = [r for r in csv.DictReader(open(csv_path)) if r["ok"] == "True"]
    designs = {d["name"]: d for d in json.load(open(ROOT / "results/freeform/designs_all.json"))}
    by = {}
    for r in rows:
        by.setdefault(r["name"], {})[int(round(float(r["alpha_deg"])))] = r
    out = []
    for name, v in by.items():
        if 0 in v and 10 in v:
            out.append({"name": name, "design": designs[name], "CdA": float(v[0]["CdA_m2"]),
                        "Cm_alpha": (float(v[10]["Cm_conf"]) - float(v[0]["Cm_conf"])) / 10.0,
                        "projected_area": float(v[0]["projected_area_m2"]), "porosity": float(v[0]["porosity_proj"] or 0),
                        "height": float(v[0]["height_m"]), "converged": v[0]["converged"] == "True"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "results/freeform/server/cfd_free.csv"))
    a = ap.parse_args()
    from scipy.stats import spearmanr
    from chutesim.config import load_config
    from chutesim.cutouts import build_any_geometry
    from chutesim.freeform import free_features
    from cfd.batch import _design
    from cfd.fitmodel import make_gp
    from ddd.free import FreeDescentModel
    cfg = load_config(None)
    OUT.mkdir(parents=True, exist_ok=True)
    data = load(a.csv)
    model0 = FreeDescentModel(None, None, cfg)
    for d in data:
        g = build_any_geometry(_design(d["design"]), cfg)
        d.update(free_features(g))
        d["speed"] = float(model0.speed(np.array([d["CdA"]]))[0])
        d["family"] = "free" if "free" in d["design"] else ("cut" if d["design"].get("cut") else "ref")
    with open(OUT / "free_table.csv", "w", newline="") as f:
        keys = [k for k in data[0] if k != "design"]
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows({k: d[k] for k in keys} for d in data)
    free = [d for d in data if d["family"] == "free"]
    W = np.array([d["design"]["free"] for d in free])
    cda = np.array([d["CdA"] for d in free])
    cma = np.array([d["Cm_alpha"] for d in free])
    print(f"{len(data)} designs with both angles ({len(free)} free-form)")
    # surrogate comparison, leave-one-out (course wk 6)
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import PolynomialFeatures, StandardScaler
    makers = {"linear": lambda: make_pipeline(StandardScaler(), LinearRegression()),
              "quadratic": lambda: make_pipeline(StandardScaler(), PolynomialFeatures(2), Ridge(1.0)),
              "gp": lambda: make_gp(W.shape[1]),
              "forest": lambda: RandomForestRegressor(300, min_samples_leaf=2, random_state=0)}
    cv = {}
    for tname, y in (("CdA", cda), ("Cm_alpha", cma)):
        for mname, mk in makers.items():
            pred = np.array([mk().fit(np.delete(W, i, 0), np.delete(y, i)).predict(W[i:i + 1])[0] for i in range(len(y))])
            cv[f"{tname}/{mname}"] = {"rmse": float(np.sqrt(np.mean((pred - y) ** 2))), "spearman": float(spearmanr(pred, y)[0]),
                                      "range": float(y.max() - y.min())}
            print(f"  {tname:9s} {mname:9s} rmse={cv[f'{tname}/{mname}']['rmse']:.3g} rho={cv[f'{tname}/{mname}']['spearman']:.3f}")
    (OUT / "surrogate_cv.json").write_text(json.dumps(cv, indent=1))
    m = FreeDescentModel(make_gp(W.shape[1]).fit(W, cda), make_gp(W.shape[1]).fit(W, cma), cfg)
    pickle.dump(m, open(OUT / "free_model.pkl", "wb"))
    # Sobol on the GP (course wk 2: main + interaction effects), ignoring feasibility
    from ddd.sensitivity import sobol_indices
    lb, ub = -1.6 * np.ones(W.shape[1]), 1.6 * np.ones(W.shape[1])
    sob = {}
    for tname, f in (("speed", lambda X: m.predict(X)[0]), ("Cm_alpha", lambda X: m.predict(X)[1])):
        r = sobol_indices(f, lb, ub, N=4000, seed=0)
        sob[tname] = {k: (np.asarray(v).tolist() if hasattr(v, "__len__") else v) for k, v in r.items()}
    (OUT / "sobol.json").write_text(json.dumps(sob, indent=1, default=float))
    figures(data, cv)


def figures(data, cv):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from chutesim.config import load_config
    from chutesim.cutouts import build_any_geometry
    from cfd.batch import _design
    cfg = load_config(None)
    col = {"free": "#4c72b0", "cut": "#dd8452", "ref": "#2a2a2a"}
    fig, axs = plt.subplots(1, 3, figsize=(17, 5.2))
    for fam in ("free", "cut", "ref"):
        D = [d for d in data if d["family"] == fam]
        if not D:
            continue
        axs[0].scatter([d["open_frac"] * 100 for d in D], [d["CdA"] * 1e4 for d in D], c=col[fam], label=fam, s=30)
        axs[1].scatter([d["speed"] for d in D], [d["Cm_alpha"] * 1e3 for d in D], c=col[fam], label=fam, s=30)
        axs[2].scatter([d["projected_area"] * 1e4 for d in D], [d["CdA"] * 1e4 for d in D], c=col[fam], label=fam, s=30)
    axs[0].set_xlabel("open area (holes) [% of outline]"); axs[0].set_ylabel("drag area CdA [cm²]")
    axs[0].set_title("Drag vs geometric porosity")
    axs[1].set_xlabel("predicted pre-impact speed after 4 m [m/s] (lower = better)")
    axs[1].set_ylabel("Cm_alpha [1e-3 / deg] (lower = more stable)")
    axs[1].axhline(0, c="k", lw=.7)
    axs[1].set_title("Descent speed vs stability (CFD)")
    axs[2].set_xlabel("inflated projected area [cm²]"); axs[2].set_ylabel("CdA [cm²]")
    axs[2].set_title("What drives drag")
    for ax in axs:
        ax.legend(fontsize=8)
        ax.grid(alpha=.3)
    fig.suptitle("Free-form + cut-out canopies, OpenFOAM k-omega SST at 7 m/s (all 250 cm² of plastic)", weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "free_cfd_overview.png", dpi=130)
    # gallery: best 8 and worst 8 by speed
    srt = sorted(data, key=lambda d: d["speed"])
    pick = srt[:8] + srt[-8:]
    fig, axs = plt.subplots(2, 8, figsize=(20, 5.6))
    for ax, d in zip(axs.ravel(), pick):
        g = build_any_geometry(_design(d["design"]), cfg)
        o = np.vstack([g.outline, g.outline[:1]]) * 100
        ax.fill(o[:, 0], o[:, 1], color="#2e7d32" if d in srt[:8] else "#c62828", alpha=.35, ec="k", lw=.8)
        for h in getattr(g, "holes", []):
            hh = np.vstack([h, h[:1]]) * 100
            ax.fill(hh[:, 0], hh[:, 1], color="white", ec="k", lw=.6)
        for s in g.slits:
            ax.plot(s[:, 0] * 100, s[:, 1] * 100, "r", lw=1)
        ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(f"{d['name']}\n{d['speed']:.3f} m/s, Cm' {d['Cm_alpha'] * 1e3:+.1f}", fontsize=8)
    fig.suptitle("CFD: 8 slowest (green) and 8 fastest (red) canopies", weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "free_best_worst.png", dpi=110)


if __name__ == "__main__":
    main()
