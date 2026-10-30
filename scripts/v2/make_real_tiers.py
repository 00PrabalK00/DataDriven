"""Pick the real-drop test designs (best / middle / worst tiers) and produce cutting templates + drop schedule.

Ranking: the CFD surrogate's noise-free predicted pre-impact speed (results/cfd/surrogate/descent_model.pkl)
over a dense Latin-hypercube sample of the design space; designs inside a tier are spread out (maximin in the
normalised design space) so each tier is not six copies of the same canopy. If the full-simulator screen
(results/screen_v2/screen_valid.csv) exists, each chosen design's nearest screened design is reported as a
cross-check. Output: results/real_test_v2/ (tiers.csv, templates/*.svg, drop_schedule.csv, tiers.png, README.md).
  python/.venv/bin/python scripts/v2/make_real_tiers.py [--per-tier 6] [--reps 3]
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
from chutesim.config import load_config  # noqa: E402
from chutesim.geometry import Design, build_geometry  # noqa: E402

LB, UB = np.array([2.0, 0.0, 0.25]), np.array([8.0, 0.25, 0.65])


def spread_pick(X, k, start=0):
    """Greedy maximin selection of k rows of X (normalised), starting from row `start`."""
    Z = (X - LB) / (UB - LB)
    sel = [start]
    d = np.linalg.norm(Z - Z[start], axis=1)
    while len(sel) < k:
        i = int(np.argmax(d)); sel.append(i); d = np.minimum(d, np.linalg.norm(Z - Z[i], axis=1))
    return sel


def svg(g, title, path):
    o = g.outline * 1000
    S = g.slits * 1000
    R = float(np.abs(o).max()) + 12
    W = 2 * R
    pts = " ".join(f"{x:.3f},{-y:.3f}" for x, y in o)
    sl = "".join(f'<line x1="{a[0]:.3f}" y1="{-a[1]:.3f}" x2="{b[0]:.3f}" y2="{-b[1]:.3f}" stroke="red" stroke-width="0.3"/>' for a, b in S)
    att = "".join(f'<circle cx="{p[0]*1000:.2f}" cy="{-p[1]*1000:.2f}" r="1.2" fill="none" stroke="blue" stroke-width="0.25"/>' for p in g.attach_points) if hasattr(g, "attach_points") else ""
    path.write_text(f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W:.2f}mm" height="{W + 16:.2f}mm" viewBox="{-R:.2f} {-R:.2f} {W:.2f} {W + 16:.2f}">
<polygon fill="none" stroke="black" stroke-width="0.25" points="{pts}"/>{sl}{att}
<circle cx="0" cy="0" r="0.8" fill="none" stroke="black" stroke-width="0.2"/>
<text x="{-R + 3:.1f}" y="{R + 5:.1f}" font-size="3.2">{title}</text>
<text x="{-R + 3:.1f}" y="{R + 9.5:.1f}" font-size="2.6">net area {g.area_net * 1e4:.2f} cm2 | black = cut outline, red = slit cuts, blue = line attachment points | print at 100%</text>
<line x1="{-R + 3:.1f}" y1="{R + 12.5:.1f}" x2="{-R + 53:.1f}" y2="{R + 12.5:.1f}" stroke="black" stroke-width="0.4"/><text x="{-R + 55:.1f}" y="{R + 13.5:.1f}" font-size="2.6">50 mm scale check</text>
</svg>''')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-tier", type=int, default=6)
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    cfg = load_config(None)
    m = pickle.load(open(ROOT / "results/cfd/surrogate/descent_model.pkl", "rb"))
    rng = np.random.default_rng(42)
    X = LB + rng.random((6000, 3)) * (UB - LB)
    X = np.array([x for x in X if build_geometry(Design(*x), cfg).feasible])
    v, cma = m(X)
    order = np.argsort(v)
    n = len(order)
    pools = {"best": order[: n // 20], "middle": order[n // 2 - n // 40: n // 2 + n // 40], "worst": order[-n // 20:]}
    out = ROOT / "results/real_test_v2"
    (out / "templates").mkdir(parents=True, exist_ok=True)
    screen = None
    sp = ROOT / "results/screen_v2/screen_valid.csv"
    if sp.exists():
        S = list(csv.DictReader(open(sp)))
        screen = (np.array([[float(r["q"]), float(r["slit_len"]), float(r["slit_r"])] for r in S]), np.array([float(r["score"]) for r in S]))
    rows = []
    for tier, idx in pools.items():
        P = X[idx]
        best_in_pool = int(np.argmin(v[idx])) if tier != "worst" else int(np.argmax(v[idx]))
        for j, s in enumerate(spread_pick(P, a.per_tier, best_in_pool)):
            x = P[s]
            code = f"{tier[0].upper()}{j + 1}"
            row = {"code": code, "tier": tier, "q": round(float(x[0]), 3), "slit_len": round(float(x[1]), 4), "slit_r": round(float(x[2]), 3),
                   "pred_speed_cfd_surrogate": round(float(m(x[None])[0][0]), 4), "pred_Cm_alpha": float(m(x[None])[1][0])}
            if screen is not None:
                k = int(np.argmin(np.linalg.norm(((screen[0] - x) / (UB - LB)), axis=1)))
                row["nearest_screened_full_sim_score"] = round(float(screen[1][k]), 4)
            rows.append(row)
            g = build_geometry(Design(*x), cfg)
            svg(g, f"{code} ({tier}): q={x[0]:.2f}, slit len {x[1]:.3f}, slit r {x[2]:.2f}", out / "templates" / f"{code}.svg")
    with open(out / "tiers.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    # randomised blocks: every block drops every design once
    sched, k = [], 0
    r2 = np.random.default_rng(7)
    for b in range(1, a.reps + 1):
        for c in r2.permutation([r["code"] for r in rows]):
            k += 1; sched.append({"drop": k, "block": b, "design": c, "notes": ""})
    with open(out / "drop_schedule.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["drop", "block", "design", "notes"]); w.writeheader(); w.writerows(sched)
    # figure: outlines per tier
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(3, a.per_tier, figsize=(2.6 * a.per_tier, 8.4))
    col = {"best": "#2e7d32", "middle": "#f9a825", "worst": "#c62828"}
    for ax, r in zip(axs.ravel(), rows):
        g = build_geometry(Design(r["q"], r["slit_len"], r["slit_r"]), cfg)
        o = np.vstack([g.outline, g.outline[:1]]) * 100
        ax.fill(o[:, 0], o[:, 1], color=col[r["tier"]], alpha=0.25, ec=col[r["tier"]], lw=1.5)
        for s in g.slits:
            ax.plot(s[:, 0] * 100, s[:, 1] * 100, color="k", lw=1.6)
        ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(f"{r['code']}: {r['pred_speed_cfd_surrogate']:.3f} m/s\nq={r['q']:.1f} slit {r['slit_len']:.2f}", fontsize=9)
    fig.suptitle("Real-drop test designs (all 250 cm²): best / middle / worst tiers by the CFD surrogate (predicted pre-impact speed)", fontsize=11, weight="bold")
    fig.tight_layout(); fig.savefig(out / "tiers.png", dpi=140)
    print(json.dumps(rows, indent=0)[:1500])
    print(f"{len(rows)} designs, {len(sched)} drops -> {out}")


if __name__ == "__main__":
    main()
