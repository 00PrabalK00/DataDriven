"""Variance-based (Sobol) sensitivity and two-variable response maps.

Port of matlab/+chute/+analysis/{sobolIndices, interactionPlot}.m. Saltelli sampling (matrices A, B and
A_B^(i)), first-order index by the Saltelli (2010) estimator, total index by the Jansen estimator.
Outputs are centred (mean of f over A and B subtracted) before estimating: without it, the estimators
lose all precision when the mean (e.g. ~6.85 m/s descent speed) is large relative to the variation.
"""
from __future__ import annotations

import numpy as np


def ishigami(X, a=7.0, b=0.1):
    """Ishigami test function on [-pi, pi]^3: S = (0.314, 0.442, 0), ST = (0.558, 0.442, 0.244)."""
    X = np.atleast_2d(X)
    return np.sin(X[:, 0]) + a * np.sin(X[:, 1]) ** 2 + b * X[:, 2] ** 4 * np.sin(X[:, 0])


def sobol_indices(f, lb, ub, N: int = 4000, seed: int = 0, sampler: str = "random", n_boot: int = 0):
    """f: vectorised callable X (n, d) -> (n,). Returns dict first, total, interaction (arrays), N,
    and (if n_boot > 0) 95% bootstrap intervals first_ci / total_ci of shape (2, d).
    Cost: N * (d + 2) evaluations of f. sampler 'random' (as MATLAB) or 'sobol' (scrambled QMC)."""
    lb = np.asarray(lb, float); ub = np.asarray(ub, float)
    d = len(lb)
    if sampler == "sobol":
        from scipy.stats import qmc
        U = qmc.Sobol(2 * d, scramble=True, seed=seed).random(N)
        UA, UB = U[:, :d], U[:, d:]
    else:
        rng = np.random.default_rng(seed)
        UA, UB = rng.random((N, d)), rng.random((N, d))
    A = lb + UA * (ub - lb)
    B = lb + UB * (ub - lb)
    fA = np.asarray(f(A), float).ravel()
    fB = np.asarray(f(B), float).ravel()
    f0 = np.mean(np.r_[fA, fB])
    fA, fB = fA - f0, fB - f0
    fAB = np.empty((N, d))
    for i in range(d):
        ABi = A.copy(); ABi[:, i] = B[:, i]
        fAB[:, i] = np.asarray(f(ABi), float).ravel() - f0

    def est(idx):
        a, b, ab = fA[idx], fB[idx], fAB[idx]
        V = np.var(np.r_[a, b], ddof=1)
        S1 = np.mean(b[:, None] * (ab - a[:, None]), 0) / V
        ST = 0.5 * np.mean((a[:, None] - ab) ** 2, 0) / V
        return S1, ST

    S1, ST = est(np.arange(N))
    out = {"first": S1, "total": ST, "interaction": ST - S1, "N": N, "n_evals": N * (d + 2)}
    if n_boot:
        rng = np.random.default_rng(seed + 1)
        bs = [est(rng.integers(0, N, N)) for _ in range(n_boot)]
        out["first_ci"] = np.percentile([b[0] for b in bs], [2.5, 97.5], axis=0)
        out["total_ci"] = np.percentile([b[1] for b in bs], [2.5, 97.5], axis=0)
    return out


def interaction_plot(f, lb, ub, names, file, subtitle: str = "", n_grid: int = 40, label: str = "response"):
    """Two-variable response maps of f (other variables at mid-range) for all pairs; PNG at 150 dpi."""
    import itertools

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    lb = np.asarray(lb, float); ub = np.asarray(ub, float)
    pairs = list(itertools.combinations(range(len(lb)), 2))
    mid = (lb + ub) / 2
    fig, axes = plt.subplots(1, len(pairs), figsize=(4.2 * len(pairs), 3.6), constrained_layout=True)
    axes = np.atleast_1d(axes)
    for ax, (i, j) in zip(axes, pairs):
        a, b = np.meshgrid(np.linspace(lb[i], ub[i], n_grid), np.linspace(lb[j], ub[j], n_grid))
        X = np.tile(mid, (a.size, 1)); X[:, i] = a.ravel(); X[:, j] = b.ravel()
        Z = np.asarray(f(X), float).reshape(a.shape)
        cs = ax.contourf(a, b, Z, 20, cmap="viridis")
        fig.colorbar(cs, ax=ax, label=label)
        ax.set_xlabel(names[i]); ax.set_ylabel(names[j])
    fig.suptitle("Response maps (surrogate)" + (f"\n{subtitle}" if subtitle else ""), fontsize=10)
    fig.savefig(file, dpi=150)
    plt.close(fig)
