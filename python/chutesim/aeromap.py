"""Geometry -> aerodynamic parameter maps.

prior-v1 is a HEURISTIC PLACEHOLDER (evidence level L2). Every relation below is an assumption
chosen to exercise the software, not a measured or validated aerodynamic law. Optimizers that search
this map will rediscover the preferences encoded here. Slits do not open in the rigid simulated
canopy; their entire effect enters through this map. Real conclusions require calibration (fittedMap)
and validation on separate physical drops.
"""
from __future__ import annotations

import json
import math

from .geometry import Geometry, geometry_features

PRIOR_VERSION = "prior-v1"


def prior_map(g: Geometry, cfg: dict) -> dict:
    f = geometry_features(g)
    A0 = g.A0
    corner = 1.0 - f["c_iso"]                       # 0 circle, ~0.17 at q=8
    s = f["slit_total_len_norm"] * math.exp(-((f["slit_mid_r_norm"] - 0.45) / 0.15) ** 2)
    osc = (0.25 + 1.2 * corner) / (1.0 + 4.0 * s)  # oscillation intensity (assumed)
    phi = f["porosity_proxy"]
    K_open = A0 * 0.80 * 0.75 * (1 + 0.35 * corner) * (1 - 2.5 * phi) * (1 - 0.25 * osc)
    tau = 0.12 * (1 + 0.8 * corner) * (1 + 3.0 * phi)
    p_fail = min(0.5, 0.02 + 0.3 * corner + 4.0 * phi)
    return {
        "model": PRIOR_VERSION,
        "evidence_level": "L2",
        "K_open_m2": K_open,
        "tau_s": tau,
        "osc_intensity": osc,
        "osc_tau_s": 0.3,
        "rot_damping": 2e-4 * (1 + 2 * s),
        "align_gain": 0.3,
        "p_deploy_fail": p_fail,
        "K_fail_frac": 0.35,
        "features": f,
    }


class FittedMap:
    """Same interface as prior_map, backed by a calibration-fit file (GP/linear predictions exported
    from MATLAB +calib). Placeholder until physical calibration data exist."""

    def __init__(self, path):
        with open(path) as fh:
            self.spec = json.load(fh)
        self.version = self.spec["version"]

    def __call__(self, g: Geometry, cfg: dict) -> dict:
        base = prior_map(g, cfg)
        f = base["features"]
        out = dict(base)
        for key, lin in self.spec["linear"].items():
            out[key] = lin["b0"] + sum(lin["b"][k] * f[k] for k in lin["b"])
        out["model"] = self.version
        out["evidence_level"] = self.spec.get("evidence_level", "L3")
        return out


def get_map(cfg: dict):
    m = cfg["aero"]["model"]
    if m == PRIOR_VERSION:
        return prior_map, PRIOR_VERSION
    fm = FittedMap(cfg["aero"]["fit_file"])
    return fm, fm.version
