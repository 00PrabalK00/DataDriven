"""Free-form surrogate environment: field weights (D6, 9 numbers) -> (pre-impact speed, Cm_alpha).

GPs trained on the CFD batch predict CdA and the pitch-stability slope Cm_alpha from generic shape features
(FEATURES below; raw weights predicted far worse: leave-one-out rank correlation 0.25-0.57 vs 0.80 for CdA);
the speed after the drop height follows in closed form (same physics as cfd.fitmodel.DescentModel).
Every request is first checked against the fabrication rules (chutesim.freeform: one piece, minimum hole
size, minimum bridge, no hole at the line points); an uncuttable design gets the marked penalty and status
"infeasible_geometry", exactly like an infeasible geometry in the simulator benchmark. Optionally (clf) a
classifier trained on form-finding runs rejects designs predicted not to inflate to a steady shape, with the
same penalty and status: steady CFD values of such shapes are meaningless.
"""
from __future__ import annotations

import numpy as np

from .envs import SurrogateEnv, _result

W_MAX = 1.6
PENALTY = 10.0
FEATURES = ["c_iso", "max_radius_norm", "outline_radius_norm", "open_frac", "n_holes", "open_r_norm", "open_perimeter_norm"]


class FreeDescentModel:
    def __init__(self, model_cda, model_cma, cfg: dict, sym: str = "D6", clf=None):
        from chutesim.payload import frontal_area
        self.m_cda, self.m_cma, self.sym, self.clf = model_cda, model_cma, sym, clf
        self.cfg = {k: cfg[k] for k in ("canopy", "payload", "freeform", "drop") if k in cfg}
        self.mass = cfg["payload"]["mass_kg"] + cfg["canopy"]["mass_kg"]
        self.k_box = cfg["payload"]["Cd_box"] * frontal_area(cfg["payload"])
        self.h = cfg["drop"]["height_m"]
        self.rho = 1.2
        self._feas: dict = {}

    def geometry_info(self, w):
        """(feasible, feature row) of one design, cached."""
        k = tuple(np.round(np.asarray(w, float), 12))
        if k not in self._feas:
            from chutesim.freeform import build_free_geometry, free_design, free_features
            g = build_free_geometry(free_design(k, self.sym), self.cfg)
            ok = bool(g.feasible)
            if ok and self.clf is not None:
                ok = bool(self.clf.predict_proba(np.array([k]))[0, 1] > 0.5)
            f = free_features(g)
            self._feas[k] = (ok, [f[n] for n in FEATURES])
        return self._feas[k]

    def feasible(self, w) -> bool:
        return self.geometry_info(w)[0]

    def speed(self, cda):
        K = np.maximum(cda, 1e-4) + self.k_box
        vt = np.sqrt(2 * self.mass * 9.81 / (self.rho * K))
        return vt * np.sqrt(1 - np.exp(-2 * 9.81 * self.h / vt**2))

    def predict(self, X):
        """Noise-free (speed, Cm_alpha) ignoring feasibility (for plots / re-scoring)."""
        F = np.array([self.geometry_info(x)[1] for x in np.atleast_2d(np.asarray(X, float))])
        return self.speed(self.m_cda.predict(F)), self.m_cma.predict(F)

    def __call__(self, X):
        X = np.atleast_2d(np.asarray(X, float))
        ok = np.array([self.feasible(x) for x in X])
        v, cma = self.predict(X)
        return np.where(ok, v, PENALTY), np.where(ok, cma, PENALTY), ok


class FreeEnv(SurrogateEnv):
    """Surrogate environment over the D6 field weights; bounds [-1.6, 1.6]^9 (the DOE range)."""
    zero_slit_r = None

    def __init__(self, model: FreeDescentModel, noise_sd: float = 0.0, fail_prob: float = 0.0, rng=None):
        super().__init__(model, noise_sd, fail_prob, rng, penalty=PENALTY)
        from chutesim.freeform import n_weights
        d = n_weights(model.sym)
        self.bounds = (-W_MAX * np.ones(d), W_MAX * np.ones(d))

    def __call__(self, X):
        X = np.atleast_2d(np.asarray(X, float))
        n = X.shape[0]
        score, sec, ok = self.model(X)
        score, sec = np.asarray(score, float).copy(), np.asarray(sec, float).copy()
        status = np.where(ok, "ok", "infeasible_geometry").astype(object)
        if self.noise_sd > 0:
            score[ok] += self.noise_sd * self.rng.standard_normal(int(ok.sum()))
        if self.fail_prob > 0:
            bad = ok & (self.rng.random(n) < self.fail_prob)
            status[bad] = "infeasible_sensing"
            score[bad] = sec[bad] = self.penalty
        return _result(score, sec, status, drops=np.zeros(n), mean_speed=np.where(status == "ok", score, np.nan))


def free_env(model_path, noise_sd: float = 0.0, fail_prob: float = 0.0, rng=None) -> FreeEnv:
    import pickle
    return FreeEnv(pickle.load(open(model_path, "rb")), noise_sd, fail_prob, rng)
