"""Design of experiments: feasible maximin LHS, centered L2 discrepancy, randomised drop schedule.

Port of matlab/+chute/+doe/{bounds, isFeasible, lhsDesigns, centeredL2Discrepancy, dropSchedule}.m.
MATLAB's lhsdesign('criterion','maximin','iterations',50) is replaced by the best (largest min distance)
of 50 scipy.stats.qmc LatinHypercube draws; the greedy maximin subset selection is identical.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.distance import cdist, pdist

DEFAULT_BASELINES = ((2.0, 0.0, 0.45), (4.0, 0.0, 0.45))


def bounds(cfg: dict | None = None):
    from .latent import param3_bounds
    return param3_bounds(cfg)


def is_feasible(X, cfg: dict | None = None):
    """Fabrication/geometry feasibility of rows [q, slit_len, slit_r] via the shared geometry code."""
    from chutesim.geometry import Design, build_geometry
    if cfg is None:
        from chutesim.config import load_config
        cfg = load_config()
    ok, reasons = [], []
    for x in np.atleast_2d(X):
        g = build_geometry(Design(*map(float, x)), cfg)
        ok.append(g.feasible); reasons.append(list(g.reasons))
    return np.array(ok, bool), reasons


def maximin_lhs(n: int, d: int, seed: int = 0, iterations: int = 50) -> np.ndarray:
    from scipy.stats import qmc
    rng = np.random.default_rng(seed)
    best, best_d = None, -np.inf
    for _ in range(iterations):
        U = qmc.LatinHypercube(d, seed=rng).random(n)
        m = pdist(U).min()
        if m > best_d:
            best, best_d = U, m
    return best


def centered_l2_discrepancy(X) -> float:
    """Centered L2 discrepancy of points in [0,1]^d (lower = more uniform). Equals
    sqrt(scipy.stats.qmc.discrepancy(X, method='CD'))."""
    X = np.asarray(X, float)
    n, d = X.shape
    a = np.abs(X - 0.5)
    t1 = (13 / 12) ** d
    t2 = 2 / n * np.sum(np.prod(1 + 0.5 * a - 0.5 * a**2, 1))
    s = 0.0
    for i in range(n):
        s += np.sum(np.prod(1 + 0.5 * a[i] + 0.5 * a - 0.5 * np.abs(X[i] - X), 1))
    return float(np.sqrt(t1 - t2 + s / n**2))


def lhs_designs(n: int = 16, seed: int = 1, baselines=DEFAULT_BASELINES, oversample: int = 6, cfg: dict | None = None):
    """n space-filling feasible designs + the unslit baselines. Returns (D (n+nb, 3), info)."""
    lb, ub = bounds(cfg)
    U = maximin_lhs(oversample * n, 3, seed)
    C = lb + U * (ub - lb)
    ok, _ = is_feasible(C, cfg)
    C = C[ok]
    if len(C) < n:
        raise RuntimeError(f"only {len(C)} feasible candidates")
    Z = (C - lb) / (ub - lb)
    sel = [0]
    while len(sel) < n:
        dmin = cdist(Z, Z[sel]).min(1)
        dmin[sel] = -np.inf
        sel.append(int(np.argmax(dmin)))
    B = np.asarray(baselines, float).reshape(-1, 3)
    D = np.vstack([C[sel], B])
    info = {"is_baseline": np.r_[np.zeros(n, bool), np.ones(len(B), bool)],
            "discrepancy": centered_l2_discrepancy(Z[sel]), "min_distance": float(pdist(Z[sel]).min()),
            "seed": seed}
    return D, info


def drop_schedule(D, is_baseline, n_rep: int = 3, seed: int = 0) -> list[dict]:
    """Randomised physical drop order: each of n_rep blocks has every design once in random order, so
    baselines are interleaved through the session. Rows: drop, design (1-based), repeat, q, slit_len,
    slit_r, baseline, failure_label."""
    rng = np.random.default_rng(seed)
    D = np.asarray(D, float)
    rows = []
    for b in range(1, n_rep + 1):
        for i in rng.permutation(len(D)):
            rows.append({"drop": len(rows) + 1, "design": int(i) + 1, "repeat": b, "q": D[i, 0],
                         "slit_len": D[i, 1], "slit_r": D[i, 2], "baseline": bool(is_baseline[i]),
                         "failure_label": ""})
    return rows
