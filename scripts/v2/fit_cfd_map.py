"""Fit the CFD surrogates from results/cfd/cfd_results.csv and switch the simulator to aero model cfd-v1.

Writes: config/aero/cfd_v1.pkl (CfdMap spec), results/cfd/surrogate/descent_model.pkl (fast benchmark
objective), results/cfd/surrogate/cfd_table.csv, cv.json, figures; sets config aero.model = cfd-v1.
  python/.venv/bin/python scripts/v2/fit_cfd_map.py [--no-config]
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
from chutesim.aeromap import prior_map  # noqa: E402
from chutesim.config import load_config  # noqa: E402
from chutesim.geometry import Design, build_geometry  # noqa: E402
from cfd.fitmodel import FEATURES, DescentModel, features_of, make_gp  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "results/cfd/cfd_results.csv"))
    ap.add_argument("--no-config", action="store_true")
    a = ap.parse_args()
    cfg = load_config(None)
    rows = [r for r in csv.DictReader(open(a.csv)) if r["ok"] in ("True", "true", "1")]
    by = {}
    for r in rows:
        key = (float(r["q"]), float(r["slit_len"]), float(r["slit_r"]))
        by.setdefault(key, {})[int(round(float(r["alpha_deg"])))] = r
    D, cda, cma, names = [], [], [], []
    for k, v in by.items():
        if 0 in v and 10 in v:
            D.append(k); names.append(v[0]["name"])
            cda.append(float(v[0]["CdA_m2"]))
            cma.append((float(v[10]["Cm_conf"]) - float(v[0]["Cm_conf"])) / 10.0)
    D, cda, cma = np.array(D), np.array(cda), np.array(cma)
    print(f"{len(D)} designs with both angles")
    X = features_of(D, cfg)
    out = ROOT / "results/cfd/surrogate"
    out.mkdir(parents=True, exist_ok=True)
    # leave-one-out CV for both targets
    cv = {}
    for name, y in (("CdA", cda), ("Cm_alpha", cma)):
        pred = np.empty_like(y)
        for i in range(len(y)):
            m = make_gp().fit(np.delete(X, i, 0), np.delete(y, i))
            pred[i] = m.predict(X[i:i + 1])[0]
        from scipy.stats import spearmanr
        cv[name] = {"rmse": float(np.sqrt(np.mean((pred - y) ** 2))), "range": float(y.max() - y.min()),
                    "spearman": float(spearmanr(pred, y)[0]), "mean": float(y.mean())}
        cv[name + "_pred"] = pred.tolist()
    m_cda, m_cma = make_gp().fit(X, cda), make_gp().fit(X, cma)
    # oscillation reference: the prior's oscillation level at the median design
    g_med = build_geometry(Design(*np.median(D, 0)), cfg)
    spec = {"features": FEATURES, "model_cda": m_cda, "model_cma": m_cma,
            "osc": {"osc_ref": float(prior_map(g_med, cfg)["osc_intensity"]), "cma_ref": float(np.median(cma)), "gain": 1.0},
            "n_designs": int(len(D)), "cv": {k: v for k, v in cv.items() if not k.endswith("_pred")}}
    (ROOT / "config/aero").mkdir(parents=True, exist_ok=True)
    pickle.dump(spec, open(ROOT / "config/aero/cfd_v1.pkl", "wb"))
    pickle.dump(DescentModel(m_cda, m_cma, cfg), open(out / "descent_model.pkl", "wb"))
    with open(out / "cfd_table.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "q", "slit_len", "slit_r", "CdA_m2", "Cm_alpha_per_deg", "CdA_loo_pred", "Cm_alpha_loo_pred"])
        for i in range(len(D)):
            w.writerow([names[i], *D[i], cda[i], cma[i], cv["CdA_pred"][i], cv["Cm_alpha_pred"][i]])
    (out / "cv.json").write_text(json.dumps({k: v for k, v in cv.items() if not k.endswith("_pred")}, indent=1))
    print(json.dumps(spec["cv"], indent=1), "osc", spec["osc"])
    # figures: parity plots + CdA / Cm_alpha over the design space
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 4, figsize=(19, 4.4))
    for j, (name, y, u) in enumerate((("CdA", cda * 1e4, "cm²"), ("Cm_alpha", cma * 1e3, "×10⁻³ /deg"))):
        p = np.array(cv[name + "_pred"]) * (1e4 if name == "CdA" else 1e3)
        ax[j].scatter(y, p, c="#1565c0", s=28)
        lo, hi = min(y.min(), p.min()), max(y.max(), p.max())
        ax[j].plot([lo, hi], [lo, hi], "k--", lw=0.8)
        ax[j].set_xlabel(f"CFD {name} [{u}]"); ax[j].set_ylabel("GP leave-one-out prediction")
        ax[j].set_title(f"{name}: LOO rmse {cv[name]['rmse'] * (1e4 if name == 'CdA' else 1e3):.2f}, rank corr {cv[name]['spearman']:.2f}")
        ax[j].grid(alpha=0.3)
    sc = ax[2].scatter(D[:, 0], D[:, 1], c=cda * 1e4, cmap="viridis", s=60, edgecolors="k")
    plt.colorbar(sc, ax=ax[2], label="CdA [cm²]"); ax[2].set_xlabel("shape q (2 = circle, 8 = rounded square)"); ax[2].set_ylabel("slit length")
    ax[2].set_title("CFD drag area over the design space")
    sc = ax[3].scatter(D[:, 0], D[:, 1], c=cma * 1e3, cmap="coolwarm", s=60, edgecolors="k")
    plt.colorbar(sc, ax=ax[3], label="Cm_alpha [×10⁻³/deg] (<0 stable)"); ax[3].set_xlabel("shape q"); ax[3].set_ylabel("slit length")
    ax[3].set_title("CFD pitch stability over the design space")
    fig.suptitle(f"CFD surrogate ({len(D)} form-found canopies, OpenFOAM k-ω SST, 7 m/s)", fontsize=12, weight="bold")
    fig.tight_layout(); fig.savefig(out / "cfd_surrogate.png", dpi=150)
    if not a.no_config:
        p = ROOT / "config/defaults.json"
        c = json.load(open(p))
        c["aero"] = {"model": "cfd-v1", "fit_file": "config/aero/cfd_v1.pkl",
                     "note": "CFD-informed (L2): CdA and pitch stability from a GP on OpenFOAM results of form-found canopies; "
                             "opening time, rotational damping and deployment failure kept from prior-v1 (assumptions)."}
        json.dump(c, open(p, "w"), indent=2)
        print("config: aero.model = cfd-v1")


if __name__ == "__main__":
    main()
