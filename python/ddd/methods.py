"""Search methods with a shared evaluation budget (port of matlab/+chute/+bench/runMethod.m and
tabuSearch.m). Every method gets the same bounds, design encoding, environment and budget; initial
sampling and finite-difference evaluations count against the budget.

MATLAB toolbox solvers are replaced by: pymoo GA / NSGA-II (ga, gamultiobj), own implementations of
simulannealbnd, particleswarm and bayesopt following MATLAB's documented defaults, scipy SLSQP with
counted finite differences (fmincon sqp).
"""
from __future__ import annotations

import warnings

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import norm

from .budget import BudgetedObjective, BudgetExhausted

METHODS = ("random", "ga", "sa", "pso", "bo", "tabu", "gradient", "moo")


def default_bounds(cfg: dict | None = None):
    """(lb, ub) for [q, slit_len, slit_r] from config canopy.bounds."""
    if cfg is None:
        from chutesim.config import load_config
        cfg = load_config()
    b = cfg["canopy"]["bounds"]
    names = ("q", "slit_len", "slit_r")
    return np.array([b[n][0] for n in names], float), np.array([b[n][1] for n in names], float)


def run_method(method: str, env, budget: int = 200, seed: int = 1, bounds=None, settings: dict | None = None) -> dict:
    rng = np.random.default_rng(seed)
    lb, ub = default_bounds() if bounds is None else (np.asarray(bounds[0], float), np.asarray(bounds[1], float))
    obj = BudgetedObjective(env, budget)
    s = dict(settings or {})
    converged, msg = False, ""
    fn = _DISPATCH.get(method.lower())
    if fn is None:
        raise ValueError(f"unknown method {method}")
    try:
        converged = bool(fn(obj, lb, ub, rng, s, seed))
    except BudgetExhausted:
        msg = "budget exhausted"
    res = obj.summary()
    res.update(method=method, seed=int(seed), budget=int(budget))
    res["endedEarly"] = bool(converged and obj.requests < budget)
    res["stopReason"] = "solver converged before the maximum budget" if res["endedEarly"] else msg
    return res


def _uniform(rng, lb, ub, n=None):
    return lb + rng.random((n, lb.size) if n else lb.size) * (ub - lb)


# ------------------------------------------------------------------------------------- random
def _random(obj, lb, ub, rng, s, seed):
    while True:
        obj.eval_vec(_uniform(rng, lb, ub, 10))


# ------------------------------------------------------------------------------- GA / NSGA-II
def _pymoo_problem(obj, lb, ub, n_obj):
    from pymoo.core.problem import Problem

    class _P(Problem):
        def __init__(self):
            super().__init__(n_var=lb.size, n_obj=n_obj, xl=lb, xu=ub)

        def _evaluate(self, X, out, *args, **kwargs):
            f, f2 = obj.eval_vec(X)
            out["F"] = f[:, None] if n_obj == 1 else np.column_stack([f, f2])
    return _P()


def _pymoo_loop(algo, problem, seed, max_stall=None):
    """ask/tell loop; stops on BudgetExhausted (raised from _evaluate) or best-F stall."""
    algo.setup(problem, seed=int(seed) % (2**32), termination=("n_gen", 10_000))
    best, stall = np.inf, 0
    while algo.has_next():
        pop = algo.ask()
        algo.evaluator.eval(problem, pop, algorithm=algo)
        algo.tell(infills=pop)
        if max_stall is not None:
            f = float(np.min(algo.opt.get("F")))
            if f < best:
                best, stall = f, 0
            else:
                stall += 1
                if stall >= max_stall:
                    break
    return True


def _ga(obj, lb, ub, rng, s, seed):
    from pymoo.algorithms.soo.nonconvex.ga import GA
    algo = GA(pop_size=s.get("PopulationSize", 20), eliminate_duplicates=True)
    return _pymoo_loop(algo, _pymoo_problem(obj, lb, ub, 1), seed, s.get("MaxStallGenerations", 50))


def _moo(obj, lb, ub, rng, s, seed):
    from pymoo.algorithms.moo.nsga2 import NSGA2
    algo = NSGA2(pop_size=s.get("PopulationSize", 20), eliminate_duplicates=True)
    return _pymoo_loop(algo, _pymoo_problem(obj, lb, ub, 2), seed)


# -------------------------------------------------------------------------- simulated annealing
def _honor_bounds(xn, x, lb, ub, rng):
    """simulannealbnd's sahonorbounds: a violated coordinate is resampled between the bound and the
    current point."""
    lo, hi = xn < lb, xn > ub
    xn = xn.copy()
    xn[lo] = lb[lo] + rng.random(lo.sum()) * (x[lo] - lb[lo])
    xn[hi] = ub[hi] - rng.random(hi.sum()) * (ub[hi] - x[hi])
    return xn


def _sa(obj, lb, ub, rng, s, seed):
    """simulannealbnd defaults: annealingfast (step length = temperature, uniform random direction),
    temperatureexp T = T0 * 0.95^k, acceptancesa 1/(1+exp(delta/max(T))), reannealing every 100
    accepted points (annealing parameters reset from a forward-difference gradient estimate)."""
    d = lb.size
    T0 = np.full(d, float(s.get("InitialTemperature", 100.0)))
    interval = int(s.get("ReannealInterval", 100))
    step_fcn = s.get("AnnealingFcn", "fast")       # 'fast' (MATLAB default) or 'boltz' (sqrt(T))
    scaled = bool(s.get("ScaleToBounds", False))   # MATLAB does not scale steps by the bound widths
    x = _uniform(rng, lb, ub)
    fx = obj.eval(x)
    k = np.zeros(d)
    T = T0.copy()
    accepted = 0
    while True:
        y = rng.standard_normal(d)
        y /= np.linalg.norm(y)
        step = T if step_fcn == "fast" else np.sqrt(T)
        if scaled:
            step = step * (ub - lb)
        xn = _honor_bounds(x + step * y, x, lb, ub, rng)
        fn = obj.eval(xn)
        delta = fn - fx
        if delta <= 0 or rng.random() < expit(-delta / max(T.max(), 1e-300)):
            x, fx = xn, fn
            accepted += 1
            if accepted % interval == 0:
                g = np.zeros(d)
                for i in range(d):
                    h = np.sqrt(np.finfo(float).eps) * max(1.0, abs(x[i]))
                    if x[i] + h > ub[i]:
                        h = -h
                    xp = x.copy()
                    xp[i] += h
                    g[i] = (obj.eval(xp) - fx) / h
                sg = np.maximum(np.abs(g), 1e-300)
                with np.errstate(divide="ignore", invalid="ignore"):
                    kn = np.log((T0 / T) * sg.max() / sg)
                k = np.where(np.isfinite(kn), np.maximum(kn, 0.0), k)
                T = T0 * 0.95 ** k
                continue
        k = k + 1
        T = T0 * 0.95 ** k


# ------------------------------------------------------------------------------------------ PSO
def _pso(obj, lb, ub, rng, s, seed):
    """particleswarm defaults: adaptive inertia in [0.1, 1.1], self/social weights 1.49, adaptive
    neighbourhood (min fraction 0.25), velocities zeroed on bound clipping."""
    S = int(s.get("SwarmSize", 15))
    w_lo, w_hi = s.get("InertiaRange", (0.1, 1.1))
    y1 = s.get("SelfAdjustmentWeight", 1.49)
    y2 = s.get("SocialAdjustmentWeight", 1.49)
    n_min = max(2, int(np.floor(S * s.get("MinNeighborsFraction", 0.25))))
    max_stall = int(s.get("MaxStallIterations", 50))
    tol = float(s.get("FunctionTolerance", 0.0))
    d = lb.size
    span = ub - lb
    x = _uniform(rng, lb, ub, S)
    v = span * (2 * rng.random((S, d)) - 1)
    f, _ = obj.eval_vec(x)
    p, fp = x.copy(), f.copy()
    ib = int(np.argmin(fp))
    b = fp[ib]
    W, c, N = w_hi, 0, n_min
    hist = [b]
    while True:
        g = np.empty_like(x)
        for i in range(S):   # neighbourhood: particle i + N-1 random others
            others = np.delete(np.arange(S), i)
            nb = np.concatenate([[i], rng.choice(others, size=min(N - 1, S - 1), replace=False)])
            g[i] = p[nb[np.argmin(fp[nb])]]
        u1, u2 = rng.random((S, d)), rng.random((S, d))
        v = W * v + y1 * u1 * (p - x) + y2 * u2 * (g - x)
        x = x + v
        out = (x < lb) | (x > ub)
        x = np.clip(x, lb, ub)
        v[out] = 0.0
        f, _ = obj.eval_vec(x)
        better = f < fp
        p[better], fp[better] = x[better], f[better]
        if f.min() < b:
            b = float(f.min())
            c = max(0, c - 1)
            N = n_min
            if c < 2:
                W = 2 * W
            elif c > 5:
                W = W / 2
            W = min(max(W, w_lo), w_hi)
        else:
            c += 1
            N = min(N + n_min, S)
        hist.append(b)
        if len(hist) > max_stall and abs(hist[-max_stall - 1] - b) / max(1.0, abs(b)) <= tol:
            return True


# --------------------------------------------------------------------------- Bayesian optimization
def _fit_gp(U, y, rng, kernel=None, fixed=False, restarts=1):
    """GP fit; `kernel` warm-starts the hyperparameter search (or is used as is when fixed)."""
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
    if kernel is None:
        kernel = (ConstantKernel(1.0, (1e-3, 1e3))
                  * Matern(length_scale=np.full(U.shape[1], 0.3), length_scale_bounds=(1e-3, 1e2), nu=2.5)
                  + WhiteKernel(1e-4, (1e-8, 1.0)))
    gp = GaussianProcessRegressor(kernel, normalize_y=True, optimizer=None if fixed else "fmin_l_bfgs_b",
                                  n_restarts_optimizer=0 if fixed else restarts,
                                  random_state=int(rng.integers(2**31)))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gp.fit(U, y)
    noise_sd = float(np.sqrt(gp.kernel_.k2.noise_level)) * float(gp._y_train_std)
    return gp, noise_sd


def _latent(gp, noise_sd, U):
    """Posterior mean and latent (noise-free) std of the objective."""
    mu, sd = gp.predict(np.atleast_2d(U), return_std=True)
    return mu, np.sqrt(np.maximum(sd ** 2 - noise_sd ** 2, 1e-18))


def _ei(gp, noise_sd, U, fmin):
    mu, sd = _latent(gp, noise_sd, U)
    z = (fmin - mu) / sd
    return (fmin - mu) * norm.cdf(z) + sd * norm.pdf(z)


def _argmax_ei(gp, noise_sd, fmin, d, rng, n_cand=2000, n_polish=5):
    C = rng.random((n_cand, d))
    ei = _ei(gp, noise_sd, C, fmin)
    best_u, best_v = C[int(np.argmax(ei))], float(ei.max())
    for u0 in C[np.argsort(-ei)[:n_polish]]:
        r = minimize(lambda u: -_ei(gp, noise_sd, u, fmin)[0], u0, method="L-BFGS-B", bounds=[(0, 1)] * d,
                     options={"maxiter": 25})
        if -r.fun > best_v:
            best_u, best_v = np.clip(r.x, 0, 1), float(-r.fun)
    return best_u


def _bo(obj, lb, ub, rng, s, seed):
    """bayesopt with expected-improvement-plus: GP (ARD Matern 5/2 + noise) on the unit cube, EI with
    the incumbent = lowest posterior mean at observed points; if the chosen point is overexploiting
    (latent std < ExplorationRatio * noise std) the kernel std is inflated (x2, up to 5 times) and EI
    re-maximized."""
    d = lb.size
    ratio = float(s.get("ExplorationRatio", 0.5))
    U, y = [], []
    warm = None

    def ev(u):
        U.append(u)
        y.append(obj.eval(lb + u * (ub - lb)))

    for _ in range(int(s.get("NumSeedPoints", 10))):
        ev(rng.random(d))
    while True:
        Ua = np.asarray(U)
        ya = np.asarray(y, float)
        fin = np.isfinite(ya)
        ya = np.where(fin, ya, ya[fin].max() if fin.any() else 1e6)
        # warm-started hyperparameters; a random restart every 10th fit
        gp, noise_sd = _fit_gp(Ua, ya, rng, kernel=warm, restarts=int(len(y) % 10 == 0))
        warm = gp.kernel_
        fmin = float(gp.predict(Ua).min())
        u = _argmax_ei(gp, noise_sd, fmin, d, rng)
        for _ in range(5):
            if _latent(gp, noise_sd, u)[1][0] >= ratio * noise_sd:
                break
            kern = gp.kernel_.clone_with_theta(gp.kernel_.theta)
            kern.k1.k1.constant_value *= 4.0       # kernel std x2
            gp, _ = _fit_gp(Ua, ya, rng, kernel=kern, fixed=True)
            u = _argmax_ei(gp, noise_sd, fmin, d, rng)
        ev(u)


# ------------------------------------------------------------------------------------- gradient
def _gradient(obj, lb, ub, rng, s, seed):
    """fmincon sqp -> scipy SLSQP; forward differences with step v*max(|x|, TypicalX) (TypicalX =
    bounds midpoint), flipped backwards at the upper bound; every FD point is a counted request."""
    v = float(s.get("FiniteDifferenceStepSize", 1e-2))
    typ = (lb + ub) / 2
    bnds = list(zip(lb, ub))
    while True:   # multistart within the budget
        last = {}

        def fun(x):
            x = np.clip(np.asarray(x, float), lb, ub)
            key = x.tobytes()
            if key not in last:
                last.clear()
                last[key] = obj.eval(x)
            return last[key]

        def jac(x):
            x = np.clip(np.asarray(x, float), lb, ub)
            f0 = fun(x)
            g = np.zeros_like(x)
            for i in range(x.size):
                h = v * max(abs(x[i]), typ[i]) * (1.0 if x[i] >= 0 else -1.0)
                if x[i] + h > ub[i] or x[i] + h < lb[i]:
                    h = -h
                xp = x.copy()
                xp[i] += h
                g[i] = (obj.eval(xp) - f0) / h
            return g

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            minimize(fun, _uniform(rng, lb, ub), jac=jac, method="SLSQP", bounds=bnds,
                     options={"maxiter": obj.budget, "ftol": 1e-6})


# ---------------------------------------------------------------------------------------- tabu
def _tabu(obj, lb, ub, rng, s, seed):
    """Tabu search over a discretized design grid. Neighbourhood: +/-1 grid step in each variable.
    Recently visited points are tabu (tenure) unless they beat the best (aspiration). Evaluated
    designs are memoized (no repeated requests for the same grid point)."""
    d = lb.size
    steps = np.asarray(s.get("steps", [0.5, 0.025, 0.05]), float)
    tenure = int(s.get("tenure", 7))
    restart_after = int(s.get("restartAfter", 10))
    levels = (np.floor((ub - lb) / steps + 1e-10) + 1).astype(int)   # numel(lb:step:ub)
    memo: dict[tuple, float] = {}

    def val(g):
        k = tuple(int(i) for i in g)
        if k not in memo:
            memo[k] = obj.eval(np.minimum(lb + (np.asarray(g) - 1) * steps, ub))
        return memo[k]

    def rand_point():
        return np.array([rng.integers(1, L + 1) for L in levels])

    n_grid = int(np.prod(levels))
    cur = rand_point()
    fcur = val(cur)
    best = fcur
    tabu: list[tuple] = []
    stall = 0
    while True:
        if len(memo) >= n_grid:   # whole grid evaluated: nothing left to request
            return True
        nb = []
        for j in range(d):
            for sgn in (-1, 1):
                g = cur.copy()
                g[j] += sgn
                if 1 <= g[j] <= levels[j]:
                    nb.append(g)
        fn = np.array([val(g) for g in nb])
        is_tabu = np.array([tuple(g) in tabu for g in nb])
        allowed = ~is_tabu | (fn < best)
        if not allowed.any():
            cur = rand_point()
            fcur = val(cur)
            continue
        fn[~allowed] = np.inf
        kmin = int(np.argmin(fn))
        tabu.append(tuple(int(i) for i in cur))
        if len(tabu) > tenure:
            tabu.pop(0)
        cur, fcur = nb[kmin], fn[kmin]
        if fcur < best:
            best, stall = fcur, 0
        else:
            stall += 1
        if stall > restart_after:   # diversification restart
            cur = rand_point()
            fcur = val(cur)
            stall = 0


_DISPATCH = {"random": _random, "ga": _ga, "sa": _sa, "pso": _pso, "bo": _bo, "tabu": _tabu,
             "gradient": _gradient, "moo": _moo}
