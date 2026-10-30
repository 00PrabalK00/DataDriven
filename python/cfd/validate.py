"""CFD validation: thin flat disc and hemispherical cup (open side facing the flow), D = 0.18 m, alpha 0.

Reference Cd (Hoerner, Fluid-Dynamic Drag, 1965, ch. 3): flat disc normal to the flow 1.17;
hollow hemisphere, concave side facing the flow 1.33-1.42 (1.42 for the thin cup).
Usage: python -m cfd.validate [--level 5] [--procs 8] [--iters 1500] [--transient]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from .case import WORK, MeshParams, SolverParams, run_stl
from .formfind import write_stl

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results" / "cfd" / "validation"
D = 0.18
REF = {"disc": (1.17, 1.17, 1.17), "cup": (1.42, 1.33, 1.42)}  # (nominal, low, high)


def disc_mesh(R: float = D / 2, nr: int = 30, z: float = 0.0):
    """Zero-thickness disc in the xy plane (polar triangulation)."""
    V = [[0, 0, z]]
    F = []
    rings = []
    for i in range(1, nr + 1):
        r = R * i / nr
        m = max(6 * i, 6)
        ids = list(range(len(V), len(V) + m))
        V += [[r * math.cos(2 * math.pi * k / m), r * math.sin(2 * math.pi * k / m), z] for k in range(m)]
        rings.append(ids)
    from scipy.spatial import Delaunay
    P = np.array(V)
    tri = Delaunay(P[:, :2]).simplices
    return P, _ccw(P, tri)


def cup_mesh(R: float = D / 2, n: int = 40):
    """Zero-thickness hemispherical shell, rim at z=0, apex at z=+R (concave side toward -z inflow)."""
    P, tri = disc_mesh(R, n)
    r = np.linalg.norm(P[:, :2], axis=1)
    # map disc radius -> polar angle (equal arc length), keep azimuth
    th = (r / R) * (math.pi / 2)
    phi = np.arctan2(P[:, 1], P[:, 0])
    X = np.column_stack([R * np.sin(th) * np.cos(phi), R * np.sin(th) * np.sin(phi), R * np.cos(th)])
    return X, tri


def _ccw(P, tri):
    a, b, c = P[tri[:, 0]], P[tri[:, 1]], P[tri[:, 2]]
    cr = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    tri = tri.copy()
    tri[cr < 0] = tri[cr < 0][:, [0, 2, 1]]
    return tri


def run(shape: str, level: int, procs: int, iters: int, transient: bool = False, tag: str = "") -> dict:
    X, F = disc_mesh() if shape == "disc" else cup_mesh()
    WORK.mkdir(parents=True, exist_ok=True)
    stl = WORK / f"val_{shape}.stl"
    write_stl(stl, X, F)
    cofr = X.mean(0)
    res = run_stl(stl, name=f"val_{shape}_L{level}{tag}", D=D, Aref=math.pi * D**2 / 4, cofr=cofr,
                  alpha_deg=0.0, n_procs=procs, mesh=MeshParams(level=level),
                  solver=SolverParams(n_iter=iters, transient=transient),
                  log_dir=OUT / f"{shape}_L{level}{tag}")
    stl.unlink(missing_ok=True)
    ref = REF[shape]
    if res.get("ok"):
        res["Cd_ref"] = ref[0]
        res["Cd_ref_range"] = [ref[1], ref[2]]
        res["err_rel"] = (res["Cd"] - ref[0]) / ref[0]
        lo, hi = ref[1], ref[2]
        res["err_to_range_rel"] = 0.0 if lo <= res["Cd"] <= hi else min(abs(res["Cd"] - lo), abs(res["Cd"] - hi)) / ref[0]
    res["shape"] = shape
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=5)
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--iters", type=int, default=1500)
    ap.add_argument("--shapes", default="disc,cup")
    ap.add_argument("--transient", action="store_true")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for s in a.shapes.split(","):
        r = run(s, a.level, a.procs, a.iters, a.transient, a.tag)
        rows.append(r)
        keys = ("shape", "Cd", "Cd_ref", "err_rel", "Cl", "drag_std_rel", "converged", "cells", "runtime_s", "solver_used")
        print(json.dumps({k: r.get(k) for k in keys}), flush=True)
        (OUT / f"{s}_L{a.level}{a.tag}.json").write_text(json.dumps(r, indent=1, default=str))


if __name__ == "__main__":
    main()
