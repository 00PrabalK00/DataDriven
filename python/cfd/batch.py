"""Batch CFD runner: designs (JSON) x alpha in {0, 10} -> results/cfd/cfd_results.csv (incremental, resumable).

designs JSON: [{"name": "...", "q": 8, "slit_len": 0.15, "slit_r": 0.45, "radial": null, "cut": null}, ...]
(cut = chutesim.cutouts tuple: [vent_frac, hole_frac, n_holes, hole_r, hole_aspect, hole_p, hole_rot_deg];
 or {"name": "...", "free": [weights...], "sym": "D6"} for a free-form design, chutesim.freeform)
Usage (server): CFD_BACKEND=native python -m cfd.batch designs.json --jobs 12 --procs 32 --level 7
Form-finding runs first (process pool), then CFD cases run `--jobs` at a time with `--procs` MPI ranks each.
A row is skipped when (design_key, alpha, level) is already in the CSV with ok=True.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import threading
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

from chutesim.config import load_config
from chutesim.geometry import Design

from .case import MeshParams, SolverParams, design_key, run_case

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results" / "cfd"
COLS = ["name", "design_key", "q", "slit_len", "slit_r", "alpha_deg", "level", "ok", "rc", "converged",
        "solver_used", "CdA_m2", "Cd", "Cl", "Cm", "Cm_conf", "drag_N", "lift_N", "force_N", "moment_Nm",
        "moment_conf_Nm", "cofr_m", "drag_std_rel", "drag_trend_rel", "projected_area_m2", "porosity_proj",
        "slit_open_area_proj_m2", "height_m", "CdA_proj_ratio", "cells", "n_procs", "runtime_s", "timings_s",
        "backend", "foam_version", "foam_build", "image", "host", "finished",
        "hole_open_area_proj_m2", "cut"]  # appended last: rows of existing CSVs keep their column order
_lock = threading.Lock()


def _design(d: dict) -> Design:
    if d.get("free") is not None:
        from chutesim.freeform import free_design
        return free_design(d["free"], d.get("sym", "D6"))
    args = (float(d.get("q", 2.0)), float(d.get("slit_len", 0.0)), float(d.get("slit_r", 0.45)),
            tuple(d["radial"]) if d.get("radial") else None)
    if d.get("cut"):
        from chutesim.cutouts import CutDesign
        return CutDesign(*args, tuple(d["cut"]))
    return Design(*args)


def done_keys(csv_path: Path) -> set:
    if not csv_path.exists():
        return set()
    with open(csv_path) as f:
        return {(r["design_key"], float(r["alpha_deg"]), int(r["level"])) for r in csv.DictReader(f) if r["ok"] == "True"}


def append_row(csv_path: Path, row: dict) -> None:
    with _lock:
        new = not csv_path.exists()
        with open(csv_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in row.items()})


def _formfind(d: dict) -> str:
    from .shapes import get_shape
    get_shape(_design(d), load_config())
    return d.get("name", d.get("id", ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("designs")
    ap.add_argument("--alphas", default="0,10")
    ap.add_argument("--jobs", type=int, default=2, help="concurrent cases")
    ap.add_argument("--procs", type=int, default=8, help="MPI ranks per case")
    ap.add_argument("--level", type=int, default=5)
    ap.add_argument("--iters", type=int, default=1500)
    ap.add_argument("--transient", action="store_true", help="pimpleFoam fallback when steady forces do not settle")
    ap.add_argument("--csv", default=str(OUT / "cfd_results.csv"))
    ap.add_argument("--ff-workers", type=int, default=min(8, os.cpu_count() or 1))
    a = ap.parse_args()
    designs = json.loads(Path(a.designs).read_text())
    alphas = [float(x) for x in a.alphas.split(",")]
    csv_path = Path(a.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    done = done_keys(csv_path)
    todo = [(d, al) for d in designs for al in alphas if (design_key(_design(d)), al, a.level) not in done]
    print(f"{len(todo)} cases to run ({len(designs) * len(alphas) - len(todo)} done)", flush=True)
    need = {design_key(_design(d)): d for d, _ in todo}
    with ProcessPoolExecutor(a.ff_workers) as ex:                 # form-finding (cached on disk)
        for f in as_completed([ex.submit(_formfind, d) for d in need.values()]):
            print("shape ready:", f.result(), flush=True)

    def job(d, al):
        des = _design(d)
        key = design_key(des)
        log_dir = OUT / "logs" / f"{d.get('name', d.get('id', key))}_a{al:g}_L{a.level}"
        t0 = time.time()
        try:
            r = run_case(des, al, a.procs, a.level, solver=SolverParams(n_iter=a.iters, transient=a.transient),
                         mesh=MeshParams(level=a.level), log_dir=log_dir)
        except Exception:
            r = {"ok": False, "rc": -1, "error": traceback.format_exc(), "design_key": key, "alpha_deg": al}
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "error.txt").write_text(r["error"])
        r.update({"name": d.get("name", d.get("id", key)), "level": a.level, "host": os.uname().nodename,
                  "finished": time.strftime("%Y-%m-%d %H:%M:%S"), "q": des.q, "slit_len": des.slit_len,
                  "slit_r": des.slit_r, "design_key": key})
        r.setdefault("ok", False)
        append_row(csv_path, r)
        (log_dir / "result.json").write_text(json.dumps(r, indent=1, default=str))
        return f"{r['name']} a={al:g}: ok={r['ok']} CdA={r.get('CdA_m2')} Cm={r.get('Cm')} {time.time() - t0:.0f}s"

    with ThreadPoolExecutor(a.jobs) as ex:
        for f in as_completed([ex.submit(job, d, al) for d, al in todo]):
            print(f.result(), flush=True)


if __name__ == "__main__":
    main()
