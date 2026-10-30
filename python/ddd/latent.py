"""Search in different design representations (port of latentSearch.m / latentEnv.m).

Representations (all with the slit knobs appended, so x = [z_1..z_k, slit_len, slit_r]):
  param3       x = [q, slit_len, slit_r]              -> [q, slit_len, slit_r] (chutesim compact design)
  pca          z = PCA scores (k)                      -> {"radial": r(theta), "slit_len", "slit_r"}
  autoencoder  z = AE code (k)                         -> idem
  vae          z ~ N(0, I) latent (k), box [-2.5, 2.5] -> idem
Latent bounds: min/max of the training-set codes (PCA, AE), +-2.5 sigma of the prior (VAE).
Decoded radial outlines are area-normalised (polar area pi in R_eq units = A0); the simulator rescales
the polygon to A0 exactly anyway. Validity (fabrication) is decided by the simulator's geometry check,
so invalid shapes still cost a request, exactly as in the MATLAB benchmark.

Nothing here runs simulations: `latent_env` wraps any env function that takes a list of designs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from . import rep


def param3_bounds(cfg: dict | None = None):
    if cfg is None:
        from chutesim.config import load_config
        cfg = load_config()
    b = cfg["canopy"]["bounds"]
    lb = np.array([b["q"][0], b["slit_len"][0], b["slit_r"][0]], float)
    ub = np.array([b["q"][1], b["slit_len"][1], b["slit_r"][1]], float)
    return lb, ub


@dataclass
class Representation:
    name: str
    k: int                                   # latent size (3 for param3: the full vector)
    lb: np.ndarray
    ub: np.ndarray
    shape_decoder: Callable | None           # Z (n, k) -> R (n, 64) radial outlines, or None for param3

    @property
    def dim(self):
        return len(self.lb)

    def decode(self, X) -> list:
        """Rows of X -> list of chutesim design objects (lists for param3, radial dicts otherwise)."""
        X = np.atleast_2d(np.asarray(X, float))
        if self.shape_decoder is None:
            return [[float(v) for v in x] for x in X]
        R = rep.normalize_area(np.atleast_2d(self.shape_decoder(X[:, :self.k])))
        return [{"radial": [float(v) for v in r], "slit_len": float(x[self.k]), "slit_r": float(x[self.k + 1])}
                for r, x in zip(R, X)]

    def decode_one(self, x):
        return self.decode(np.asarray(x, float)[None])[0]


def make_representations(R, pca: rep.PCAModel, ae: rep.AEModel | None, vae: rep.VAEModel | None,
                         k: int = 4, cfg: dict | None = None) -> dict:
    """R = training outlines (for latent bounds), models from ddd.rep. Returns {name: Representation}."""
    lb3, ub3 = param3_bounds(cfg)
    reps = {"param3": Representation("param3", 3, lb3, ub3, None)}
    Zp = pca.encode(R, k)
    reps["pca"] = Representation("pca", k, np.r_[Zp.min(0), lb3[1:]], np.r_[Zp.max(0), ub3[1:]],
                                 lambda Z: pca.decode(Z, normalize=False))
    if ae is not None:
        assert ae.k == k, "autoencoder latent size must equal k"
        Za = ae.encode(R)
        reps["autoencoder"] = Representation("autoencoder", k, np.r_[Za.min(0), lb3[1:]], np.r_[Za.max(0), ub3[1:]],
                                             lambda Z: ae.decode(Z, normalize=False))
    if vae is not None:
        assert vae.k == k, "VAE latent size must equal k"
        reps["vae"] = Representation("vae", k, np.r_[-2.5 * np.ones(k), lb3[1:]], np.r_[2.5 * np.ones(k), ub3[1:]],
                                     lambda Z: vae.decode(Z, normalize=False))
    return reps


def latent_env(decoder, base_env_fn: Callable[[list], object]) -> Callable:
    """Env over latent vectors: X (n, dim) -> base_env_fn(list of design dicts).

    `decoder` is a Representation (or any callable mapping X -> list of designs). `base_env_fn` is a
    simulator-like env taking a list of designs (e.g. a closure around chutesim Evaluator.evaluate)."""
    dec = decoder.decode if isinstance(decoder, Representation) else decoder

    def env(X):
        return base_env_fn(dec(X))
    env.decoder = decoder
    return env


def check_designs(designs: list, cfg: dict | None = None) -> list[dict]:
    """Geometry check of decoded designs with the simulator's own code (no simulation):
    net area in cm^2, feasible flag, reasons."""
    from chutesim.evaluate import design_from
    from chutesim.geometry import build_geometry
    if cfg is None:
        from chutesim.config import load_config
        cfg = load_config()
    out = []
    for d in designs:
        g = build_geometry(design_from(d), cfg)
        out.append({"area_cm2": g.area_net * 1e4, "feasible": bool(g.feasible), "reasons": list(g.reasons)})
    return out
