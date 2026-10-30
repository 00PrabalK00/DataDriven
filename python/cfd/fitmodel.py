"""CFD results -> surrogate models (shared by the simulator's cfd-v1 aero map and the fast surrogate benchmark).

Per design: CdA at alpha = 0 and the pitch-stability slope about the payload anchors
Cm_alpha = (Cm_conf(10 deg) - Cm_conf(0 deg)) / 10  [1/deg]  (negative = self-righting).
Models: standardise geometry features -> GP (ARD Matern 5/2 + white noise), one per target.

DescentModel is the picklable fast objective for the surrogate-environment benchmark: closed-form speed after
a 4 m fall with drag area K = CdA(design) + payload drag area (score, minimise) and Cm_alpha (secondary, minimise).
"""
from __future__ import annotations

import math

import numpy as np

FEATURES = ["c_iso", "slit_total_len_norm", "slit_mid_r_norm", "porosity_proxy", "max_radius_norm", "outline_radius_norm"]


def features_of(designs, cfg) -> np.ndarray:
    from chutesim.geometry import Design, build_geometry, geometry_features
    rows = []
    for d in designs:
        f = geometry_features(build_geometry(Design(float(d[0]), float(d[1]), float(d[2])), cfg, check=False))
        rows.append([f[k] for k in FEATURES])
    return np.array(rows)


def make_gp(n_inputs: int | None = None):
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    k = ConstantKernel(1.0) * Matern(length_scale=np.ones(n_inputs or len(FEATURES)), nu=2.5) + WhiteKernel(1e-3)
    return make_pipeline(StandardScaler(), GaussianProcessRegressor(k, normalize_y=True, n_restarts_optimizer=5, random_state=0))


class DescentModel:
    """Fast surrogate objective: X (n,3) [q, slit_len, slit_r] -> (score = speed after h metres, secondary = Cm_alpha)."""

    def __init__(self, model_cda, model_cma, cfg):
        from chutesim.payload import frontal_area
        self.m_cda, self.m_cma = model_cda, model_cma
        self.cfg = {"canopy": cfg["canopy"], "payload": cfg["payload"]}
        self.mass = cfg["payload"]["mass_kg"] + cfg["canopy"]["mass_kg"]
        self.k_box = cfg["payload"]["Cd_box"] * frontal_area(cfg["payload"])
        self.h = cfg["drop"]["height_m"]
        self.rho = 1.2

    def __call__(self, X):
        X = np.atleast_2d(np.asarray(X, float))
        F = features_of(X, self.cfg)
        K = np.maximum(self.m_cda.predict(F), 1e-4) + self.k_box
        vt = np.sqrt(2 * self.mass * 9.81 / (self.rho * K))
        v = vt * np.sqrt(1 - np.exp(-2 * 9.81 * self.h / vt ** 2))
        return v, self.m_cma.predict(F)
