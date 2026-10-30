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


class CfdMap:
    """cfd-v1: drag area and pitch stability from a surrogate trained on OpenFOAM results (form-found
    inflated canopy, RANS k-omega SST, U = 7 m/s, alpha = 0 and 10 deg). The surrogate file (pickle, written
    by python/cfd/fit_map.py) holds models feature-vector -> CdA [m^2] and -> Cm_alpha [1/deg], the feature
    order, and the oscillation reference. K_open = predicted CdA. Oscillation intensity scales with the
    predicted pitch stability (more negative Cm_alpha = more self-righting = less swing), around the prior's
    reference level. Opening time tau, rotational damping and deployment-failure probability have no CFD
    basis: they are kept from prior-v1 and stay assumptions (evidence level L2 until real-drop calibration).
    The version string carries the surrogate file hash, so cache keys separate every refit."""

    def __init__(self, path):
        import hashlib
        import pickle
        raw = open(path, "rb").read()
        self.spec = pickle.loads(raw)
        self.version = "cfd-v1+" + hashlib.sha256(raw).hexdigest()[:16]

    def __call__(self, g: Geometry, cfg: dict) -> dict:
        import numpy as np
        base = prior_map(g, cfg)
        f = base["features"]
        x = np.array([[f[k] for k in self.spec["features"]]])
        cda = float(self.spec["model_cda"].predict(x)[0])
        cma = float(self.spec["model_cma"].predict(x)[0])
        o = self.spec["osc"]
        rel = (cma - o["cma_ref"]) / abs(o["cma_ref"])        # >0: less stable than the reference shape
        out = dict(base)
        out["K_open_m2"] = max(cda, 0.05 * g.A0)
        out["osc_intensity"] = o["osc_ref"] * min(max(1.0 + o["gain"] * rel, 0.2), 3.0)
        out["cfd_CdA_m2"] = cda
        out["cfd_Cm_alpha_per_deg"] = cma
        out["model"] = self.version
        out["evidence_level"] = "L2 (CFD-informed, uncalibrated)"
        return out


def get_map(cfg: dict):
    m = cfg["aero"]["model"]
    if m == PRIOR_VERSION:
        return prior_map, PRIOR_VERSION
    if m == "cfd-v1":
        from pathlib import Path
        from .config import REPO_ROOT
        fp = Path(cfg["aero"]["fit_file"])
        cm = CfdMap(fp if fp.is_absolute() else REPO_ROOT / fp)
        return cm, cm.version
    fm = FittedMap(cfg["aero"]["fit_file"])
    return fm, fm.version
