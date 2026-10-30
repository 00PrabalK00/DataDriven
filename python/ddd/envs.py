"""Evaluation environments: X (n, 3) -> dict(score, status, drops, cacheHits, secondary, meanSpeed).
Ports of matlab/+chute/+bench/analyticEnv.m, surrogateEnv.m and simulatorEnv.m. All environments are
picklable classes so they can be built inside worker processes."""
from __future__ import annotations

import numpy as np

# name -> (function, argmin, min value); argmin inside the default bounds
_ANALYTIC = {
    "quadratic": (lambda X: ((X[:, 0] - 5) / 6) ** 2 + ((X[:, 1] - 0.12) / 0.25) ** 2 + ((X[:, 2] - 0.45) / 0.4) ** 2,
                  (5.0, 0.12, 0.45), 0.0),
    "multimodal": (lambda X: ((X[:, 0] - 5) / 6) ** 2 + 0.3 * np.sin(3 * np.pi * X[:, 1] / 0.25) ** 2
                   + ((X[:, 2] - 0.45) / 0.4) ** 2, (5.0, 0.0, 0.45), 0.0),
    # smooth, minimum on the bounds (q = 8, slit_len = 0.25): optimizers must handle active bounds
    "edge": (lambda X: (8 - X[:, 0]) / 6 + ((X[:, 1] - 0.25) / 0.25) ** 2 + ((X[:, 2] - 0.45) / 0.4) ** 2,
             (8.0, 0.25, 0.45), 0.0),
}


def _result(score, secondary, status=None, drops=None, hits=None, mean_speed=None):
    n = len(score)
    return {"score": np.asarray(score, float), "secondary": np.asarray(secondary, float),
            "status": np.array(["ok"] * n if status is None else status, dtype=object),
            "drops": np.ones(n) if drops is None else np.asarray(drops, float),
            "cacheHits": np.zeros(n) if hits is None else np.asarray(hits, float),
            "meanSpeed": np.full(n, np.nan) if mean_speed is None else np.asarray(mean_speed, float)}


class AnalyticEnv:
    """Cheap known-optimum test objectives for validating the harness itself (evidence level L1)."""
    level = "L1"

    def __init__(self, name: str = "quadratic"):
        if name not in _ANALYTIC:
            raise ValueError(f"unknown analytic env {name}")
        self.name = name
        _, self.xmin, self.fmin = _ANALYTIC[name]

    def __call__(self, X):
        X = np.atleast_2d(np.asarray(X, float))
        f = _ANALYTIC[self.name][0](X)
        return _result(f, X[:, 1], mean_speed=f)


def analytic_env(name: str = "quadratic") -> AnalyticEnv:
    return AnalyticEnv(name)


class SurrogateEnv:
    """Frozen-surrogate environment (separate benchmark: "surrogate environment"). model: callable
    X -> (score, secondary). Optional observation noise on the score and random sensing failures
    (scored with a marked penalty)."""
    level = "L2"

    def __init__(self, model, noise_sd: float = 0.0, fail_prob: float = 0.0, rng=None, penalty: float = 10.0):
        self.model = model
        self.noise_sd = noise_sd
        self.fail_prob = fail_prob
        self.rng = rng if isinstance(rng, np.random.Generator) else np.random.default_rng(rng)
        self.penalty = penalty

    def __call__(self, X):
        X = np.atleast_2d(np.asarray(X, float))
        n = X.shape[0]
        score, sec = self.model(X)
        score = np.asarray(score, float).ravel().copy()
        sec = np.asarray(sec, float).ravel().copy()
        if self.noise_sd > 0:
            score += self.noise_sd * self.rng.standard_normal(n)
        status = np.array(["ok"] * n, dtype=object)
        if self.fail_prob > 0:
            bad = self.rng.random(n) < self.fail_prob
            status[bad] = "infeasible_sensing"
            score[bad] = self.penalty
            sec[bad] = self.penalty
        return _result(score, sec, status, drops=np.zeros(n), mean_speed=np.where(status == "ok", score, np.nan))


def surrogate_env(model, noise_sd: float = 0.0, fail_prob: float = 0.0, rng=None, **kw) -> SurrogateEnv:
    return SurrogateEnv(model, noise_sd, fail_prob, rng, **kw)


class SimulatorEnv:
    """Simulator + virtual sensors + shared estimation pipeline through chutesim.evaluate.Evaluator
    (evidence level L2: synthetic benchmark under assumed aerodynamics). The Evaluator (and its worker
    pool, or the remote pool when CHUTESIM_REMOTE is set) is created on first use."""
    level = "L2"

    def __init__(self, seeds, cfg: dict | None = None, tag: str = "bench", log_path=None, n_workers=None):
        self.seeds = [int(s) for s in seeds]
        self.cfg = cfg
        self.tag = tag
        self.log_path = log_path
        self.n_workers = n_workers
        self._ev = None

    def __getstate__(self):
        d = dict(self.__dict__)
        d["_ev"] = None
        return d

    def _evaluator(self):
        if self._ev is None:
            from chutesim.config import load_config
            from chutesim.evaluate import Evaluator
            self.cfg = self.cfg or load_config()
            self._ev = Evaluator(self.cfg, n_workers=self.n_workers, log_path=self.log_path)
        return self._ev

    def __call__(self, X):
        X = np.atleast_2d(np.asarray(X, float))
        res = self._evaluator().evaluate([tuple(map(float, x)) for x in X], self.seeds, tag=self.tag)
        n = len(res)
        score, sec, speed = np.zeros(n), np.zeros(n), np.full(n, np.nan)
        status = np.empty(n, dtype=object)
        drops, hits = np.zeros(n), np.zeros(n)
        for i, r in enumerate(res):
            o = r["objective"]
            score[i] = o["score"]
            status[i] = str(o["status"])
            drops[i] = r["simulated_drops"]
            hits[i] = r["cache_hits"]
            lat = o.get("mean_lateral_speed")
            sec[i] = lat if lat is not None else o["P_infeasible"]   # marked penalty, not a measurement
            if o.get("mean_preimpact_vz") is not None:
                speed[i] = o["mean_preimpact_vz"]
        return _result(score, sec, status, drops, hits, speed)

    def close(self):
        if self._ev is not None:
            self._ev.close()
            self._ev = None


def simulator_env(seeds, cfg: dict | None = None, tag: str = "bench", log_path=None, n_workers=None) -> SimulatorEnv:
    return SimulatorEnv(seeds, cfg, tag, log_path, n_workers)


class _PredictModel:
    """Adapter: object(s) with predict(X) -> callable X -> (score, secondary)."""

    def __init__(self, score_model, secondary_model=None):
        self.m1, self.m2 = score_model, secondary_model

    def __call__(self, X):
        y = np.asarray(self.m1.predict(X), float)
        if y.ndim == 2 and y.shape[1] >= 2:
            return y[:, 0], y[:, 1]
        sec = np.asarray(self.m2.predict(X), float).ravel() if self.m2 is not None else np.zeros(len(X))
        return y.ravel(), sec


def load_surrogate_model(path):
    """Pickled callable, object with predict(), or dict {'score': m, 'secondary': m2}."""
    import pickle
    with open(path, "rb") as f:
        m = pickle.load(f)
    if isinstance(m, dict):
        return _PredictModel(m["score"], m.get("secondary"))
    if hasattr(m, "predict"):
        return _PredictModel(m)
    return m
