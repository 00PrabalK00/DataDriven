"""Budgeted objective for one optimizer run (port of matlab/+chute/+bench/BudgetedObjective.m).

- maximum `budget` objective REQUESTS (cached evaluations still count as requests)
- three counters: requests, unique designs, actual simulated drops (+ cache hits)
- best-so-far trace and checkpoints (25/50/100/200)
- raises BudgetExhausted once the budget is used (runners catch it)
"""
from __future__ import annotations

import time

import numpy as np

CHECKPOINTS = (25, 50, 100, 200)


class BudgetExhausted(Exception):
    """Raised when an optimizer requests more evaluations than the budget allows."""


class BudgetedObjective:
    def __init__(self, env, budget: int = 200, zero_slit_r: float = 0.45):
        self.env = env                  # X (n, d) -> dict(score, status, drops, cacheHits, secondary, meanSpeed)
        self.budget = int(budget)
        self.zero_slit_r = zero_slit_r
        self.requests = 0
        self.simulated_drops = 0
        self.cache_hits = 0
        self.X: list[np.ndarray] = []
        self.F: list[float] = []
        self.F2: list[float] = []
        self.status: list[str] = []
        self.keys: list[str] = []
        self.best_trace: list[float] = []
        self.wall: list[float] = []
        self.t0 = time.perf_counter()

    def eval(self, x) -> float:
        f, _ = self.eval_vec(np.asarray(x, float).reshape(1, -1))
        return float(f[0])

    def eval_vec(self, X):
        """Evaluate rows of X; returns (f, f2). Rows beyond the budget are not evaluated: the
        part that fits is evaluated and recorded first, then BudgetExhausted is raised."""
        X = np.atleast_2d(np.asarray(X, float))
        n = X.shape[0]
        remaining = self.budget - self.requests
        if remaining <= 0:
            raise BudgetExhausted(f"evaluation budget of {self.budget} used")
        m = min(n, remaining)
        r = self.env(X[:m])
        score = np.asarray(r["score"], float).ravel()
        sec = np.asarray(r["secondary"], float).ravel()
        drops = np.asarray(r["drops"], float).ravel()
        hits = np.asarray(r["cacheHits"], float).ravel()
        status = [str(s) for s in np.asarray(r["status"]).ravel()]
        f = np.full(n, np.inf)
        f2 = np.full(n, np.inf)
        f[:m] = score
        f2[:m] = sec
        for i in range(m):
            self.requests += 1
            self.X.append(X[i].copy())
            self.F.append(float(score[i]))
            self.F2.append(float(sec[i]))
            self.status.append(status[i])
            self.keys.append(self.canonical_key(X[i]))
            self.simulated_drops += int(drops[i])
            self.cache_hits += int(hits[i])
            prev = self.best_trace[-1] if self.best_trace else np.inf
            self.best_trace.append(min(prev, float(score[i])))
            self.wall.append(time.perf_counter() - self.t0)
        if m < n:
            raise BudgetExhausted(f"evaluation budget of {self.budget} used")
        return f, f2

    evalVec = eval_vec   # MATLAB name

    def canonical_key(self, x) -> str:
        # slit length / slit radius are the last two columns in every encoding
        x = np.array(x, float)
        if x[-2] == 0:
            x[-1] = self.zero_slit_r
        return "-".join(float(v).hex() for v in x)

    def summary(self) -> dict:
        F = np.asarray(self.F, float)
        st = np.asarray(self.status, dtype=object)
        trace = np.asarray(self.best_trace, float)
        if F.size:
            ib = int(np.argmin(F))
            fbest, xbest = float(F[ib]), self.X[ib].tolist()
        else:
            fbest, xbest = np.inf, []
        best_at = [float(trace[c - 1]) if c <= trace.size else np.nan for c in CHECKPOINTS]
        return {
            "requests": self.requests,
            "uniqueDesigns": len(set(self.keys)),
            "simulatedDrops": self.simulated_drops,
            "cacheHits": self.cache_hits,
            "fbest": fbest, "xbest": xbest,
            "bestTrace": trace.tolist(),
            "validGeometryRate": float(np.mean(st != "infeasible_geometry")) if st.size else np.nan,
            "sensingFailureRate": float(np.mean(st == "infeasible_sensing")) if st.size else np.nan,
            "wall_s": time.perf_counter() - self.t0,
            "checkpoints": list(CHECKPOINTS),
            "bestAt": best_at,
            "X": [x.tolist() for x in self.X], "F": F.tolist(), "F2": list(self.F2),
            "status": list(self.status), "wall": list(self.wall),
        }
