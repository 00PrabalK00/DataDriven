"""Laptop test: one real canopy (q=8, l=0.15, r=0.45) at alpha 0 and 10 on the coarse mesh.
Usage: python -m cfd.canopy_test --level 4 --procs 5 --iters 600"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from chutesim.geometry import Design

from .case import SolverParams, run_case

OUT = Path(__file__).resolve().parents[2] / "results" / "cfd" / "canopy_test"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=4)
    ap.add_argument("--procs", type=int, default=5)
    ap.add_argument("--iters", type=int, default=600)
    a = ap.parse_args()
    d = Design(8.0, 0.15, 0.45)

    def one(al):
        r = run_case(d, al, a.procs, a.level, solver=SolverParams(n_iter=a.iters), sample=True,
                     log_dir=OUT / f"q8_l015_r045_a{al:g}_L{a.level}")
        (OUT / f"q8_l015_r045_a{al:g}_L{a.level}.json").write_text(json.dumps(r, indent=1, default=str))
        return r
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(2) as ex:
        for r in ex.map(one, (0.0, 10.0)):
            print(json.dumps({k: r.get(k) for k in ("alpha_deg", "CdA_m2", "Cd", "Cl", "Cm", "Cm_conf", "drag_std_rel",
                                                    "converged", "cells", "runtime_s", "timings_s", "rc")}), flush=True)


if __name__ == "__main__":
    main()
