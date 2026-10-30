"""Disk cache of form-found canopy shapes (results/cfd/shapes/<key>.npz), keyed by design + cfg + settings."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from chutesim.config import load_config, stable_hash

from .formfind import Canopy3D, FlatMesh, form_find

REPO = Path(__file__).resolve().parents[2]
SHAPES = REPO / "results" / "cfd" / "shapes"


def shape_key(design, cfg: dict, kw: dict) -> str:
    d = {"q": float(design.q), "slit_len": float(design.slit_len), "slit_r": float(design.slit_r),
         "radial": [float(v) for v in design.radial] if design.radial is not None else None,
         "canopy": cfg["canopy"], "anchors": cfg["payload"]["anchors_mm"], "rho": cfg["physics"]["rho"],
         "kw": kw, "ff_version": 2}
    if hasattr(design, "key_extra"):  # cut-out / free-form designs only: keys of existing shapes unchanged
        d |= design.key_extra()
    return stable_hash(d, 12)


def get_shape(design, cfg: dict | None = None, **kw) -> Canopy3D:
    """Load the inflated shape from cache or run form_find and store it."""
    cfg = cfg or load_config()
    key = shape_key(design, cfg, kw)
    f = SHAPES / f"{key}.npz"
    if f.exists():
        z = np.load(f, allow_pickle=False)
        info = json.loads(str(z["info"]))
        loops = [(z[f"sa{i}"], z[f"sb{i}"]) for i in range(int(z["nslit"]))]
        hloops = [z[f"hl{i}"] for i in range(int(z["nhole"]))] if "nhole" in z.files else []
        fm = FlatMesh(z["xy"], z["tris"], z["attach"], loops, hloops)
        return Canopy3D(z["X"], z["tris"], z["attach"], loops, z["anchors"], fm, info)
    c = form_find(design, cfg, **kw)
    SHAPES.mkdir(parents=True, exist_ok=True)
    arrs = {f"sa{i}": a for i, (a, b) in enumerate(c.slit_loops)} | {f"sb{i}": b for i, (a, b) in enumerate(c.slit_loops)}
    arrs |= {f"hl{i}": ids for i, ids in enumerate(c.flat.hole_loops)} | {"nhole": len(c.flat.hole_loops)}
    info = dict(c.info, shape_key=key)
    np.savez_compressed(f, X=c.X, tris=c.tris, attach=c.attach, anchors=c.anchors, xy=c.flat.xy,
                        nslit=len(c.slit_loops), info=json.dumps(info, default=float), **arrs)
    c.info = info
    return c
