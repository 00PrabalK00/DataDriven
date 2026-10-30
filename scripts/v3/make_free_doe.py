"""DOE for the free-form CFD study: Latin hypercube in the D6 field-weight space, fabrication-feasible designs
only, maximin-thinned to --n designs, plus the circle reference (all weights 0).
  python/.venv/bin/python scripts/v3/make_free_doe.py --n 60 --cands 240 --workers 4
Output: results/freeform/designs_free.json (batch format), designs_free.png (gallery).
"""
import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
OUT = ROOT / "results" / "freeform"
W_MAX = 1.6


def _check(w):
    from chutesim.config import load_config
    from chutesim.freeform import build_free_geometry, free_design, free_features
    g = build_free_geometry(free_design(w, "D6"), load_config(None))
    f = free_features(g)
    return g.feasible, g.reasons, f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--cands", type=int, default=240)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    from scipy.stats import qmc
    from chutesim.freeform import n_weights
    k = n_weights("D6")
    W = qmc.scale(qmc.LatinHypercube(d=k, seed=11).random(a.cands), -W_MAX * np.ones(k), W_MAX * np.ones(k))
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(_check, W, chunksize=4))
    ok = np.array([r[0] for r in res])
    print(f"feasible {ok.sum()}/{len(W)}; reasons: "
          f"{sorted({x for r in res for x in r[1]})}")
    Wf = W[ok]
    # maximin thinning in normalised weight space, starting from the design closest to the centre
    Z = Wf / W_MAX
    sel = [int(np.argmin(np.linalg.norm(Z, axis=1)))]
    d = np.linalg.norm(Z - Z[sel[0]], axis=1)
    while len(sel) < min(a.n, len(Wf)):
        i = int(np.argmax(d))
        sel.append(i)
        d = np.minimum(d, np.linalg.norm(Z - Z[i], axis=1))
    designs = [{"name": "free_circle", "free": [0.0] * k, "sym": "D6"}]
    designs += [{"name": f"free{j:02d}", "free": [float(v) for v in Wf[i]], "sym": "D6"} for j, i in enumerate(sel)]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "designs_free.json").write_text(json.dumps(designs, indent=1))
    feats = [r[2] for r, o in zip(res, ok) if o]
    holes = [feats[i]["n_holes"] for i in sel]
    print(f"{len(designs)} designs; holes per design: {np.bincount(holes)}")
    gallery(designs)


def gallery(designs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from chutesim.config import load_config
    from chutesim.freeform import build_free_geometry, free_design
    cfg = load_config(None)
    n = len(designs)
    cols = 10
    fig, axs = plt.subplots((n + cols - 1) // cols, cols, figsize=(2.2 * cols, 2.3 * ((n + cols - 1) // cols)))
    for ax in axs.ravel():
        ax.axis("off")
    for ax, d in zip(axs.ravel(), designs):
        g = build_free_geometry(free_design(d["free"], d["sym"]), cfg)
        o = np.vstack([g.outline, g.outline[:1]]) * 100
        ax.fill(o[:, 0], o[:, 1], color="#4c72b0", alpha=.4, ec="k", lw=.8)
        for h in g.holes:
            hh = np.vstack([h, h[:1]]) * 100
            ax.fill(hh[:, 0], hh[:, 1], color="white", ec="k", lw=.6)
        ax.set_aspect("equal")
        ax.set_title(d["name"], fontsize=7)
    fig.suptitle("Free-form CFD design set (Latin hypercube in field-weight space, cuttable only, 250 cm² each)",
                 weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "designs_free.png", dpi=100)


if __name__ == "__main__":
    main()
