"""2-objective hypervolume and spacing (port of matlab/+chute/+analysis/hypervolume2d.m)."""
from __future__ import annotations

import numpy as np


def hypervolume2d(F, ref):
    """Hypervolume (minimization) of the non-dominated set of points F (n, 2) w.r.t. reference point
    ref, and the spacing metric (std of consecutive distances along the front; lower = more evenly
    spread). Returns (hv, spacing, front)."""
    F = np.asarray(F, float).reshape(-1, 2)
    ref = np.asarray(ref, float)
    F = F[np.all(np.isfinite(F), axis=1) & np.all(F < ref, axis=1)]
    if F.size == 0:
        return 0.0, np.nan, np.zeros((0, 2))
    F = F[np.lexsort((F[:, 1], F[:, 0]))]
    front = [F[0]]
    for p in F[1:]:
        if p[1] < front[-1][1]:
            front.append(p)
    front = np.asarray(front)
    hv, prev2 = 0.0, ref[1]
    for p in front:
        hv += (ref[0] - p[0]) * (prev2 - p[1])
        prev2 = p[1]
    spacing = float(np.std(np.linalg.norm(np.diff(front, axis=0), axis=1), ddof=1)) if len(front) > 2 else np.nan
    return float(hv), spacing, front
