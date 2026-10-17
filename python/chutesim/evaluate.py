"""Design evaluator: design x scenario set -> simulate -> estimation worker (separate process,
observation bundle only) -> metrics -> objective. Provenance-keyed cache, parallel pool, counters.

Cache key = hash(canonical geometry [float64-hex params + polygon hash], scenario seed + scenario
distribution version, physical config, aero model version, sensor config, pipeline version, simulator
version, objective config). Full precision keys: finite-difference perturbations always miss the cache.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .config import REPO_ROOT, canonical_json, stable_hash
from .geometry import Design, build_geometry, canonicalize
from .objective import geometry_infeasible, score
from .provenance import component_hashes, environment

PY_ROOT = REPO_ROOT / "python"
DEFAULT_CACHE = REPO_ROOT / "data" / "cache"
DEFAULT_WORK = REPO_ROOT / "data" / "sim"


def design_from(obj) -> Design:
    """[q, slit_len, slit_r] or {"radial": [...], "slit_len": l, "slit_r": r} (rich encoding)."""
    if isinstance(obj, Design):
        return obj
    if isinstance(obj, dict):
        return Design(0.0, float(obj["slit_len"]), float(obj["slit_r"]), tuple(float(x) for x in obj["radial"]))
    q, l, r = map(float, obj)
    return Design(q, l, r)


def design_key_part(d: Design, cfg: dict) -> dict:
    c = canonicalize(d, cfg)
    g = build_geometry(c, cfg)
    out = {"q": float(c.q).hex(), "slit_len": float(c.slit_len).hex(), "slit_r": float(c.slit_r).hex(),
           "polygon": g.polygon_hash()}
    if c.radial is not None:
        out["radial"] = stable_hash([float(x).hex() for x in c.radial], 32)
    return out


def cache_key(d: Design, seed: int, cfg: dict, aero_version: str) -> tuple[str, dict]:
    comp = {"design": design_key_part(d, cfg), "seed": int(seed), **component_hashes(cfg, aero_version)}
    return stable_hash(comp, 32), comp


def _cache_path(root: Path, key: str) -> Path:
    return root / key[:2] / f"{key}.json"


# ---------------------------------------------------------------- estimation worker process
_WORKER = None


def _python_exe() -> str:
    exe = Path(sys.prefix) / "bin" / "python"
    return str(exe) if exe.exists() else sys.executable


_ONE_THREAD = {k: "1" for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
                                 "OPENCV_FOR_THREADS_NUM")}


def _scrubbed_env() -> dict:
    keep = {k: os.environ[k] for k in ("PATH", "HOME", "LANG") if k in os.environ}
    keep.update(_ONE_THREAD)   # one thread per process: the pool already uses every core
    keep["PYTHONPATH"] = str(PY_ROOT)
    return keep


def _worker():
    global _WORKER
    if _WORKER is None or _WORKER.poll() is not None:
        _WORKER = subprocess.Popen([_python_exe(), "-m", "pipeline.worker", "--serve"], cwd=str(PY_ROOT),
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=_scrubbed_env())
    return _WORKER


def estimate(obs_dir: str, out_dir: str, pipeline_cfg: dict) -> dict:
    w = _worker()
    w.stdin.write(json.dumps({"obs": obs_dir, "out": out_dir, "pipeline_cfg": pipeline_cfg}) + "\n")
    w.stdin.flush()
    return json.loads(w.stdout.readline())


# ---------------------------------------------------------------- one (design, seed) task
def _task(args):
    os.environ.setdefault("MUJOCO_GL", "egl")
    import cv2
    cv2.setNumThreads(1)
    from .run_drop import write_drop
    d, seed, cfg, run_root, trial, keep_frames = args
    t0 = time.time()
    r = write_drop(design_from(d), seed, cfg, run_root, trial)
    t_sim = time.time() - t0
    est_dir = str(Path(run_root) / "est" / trial)
    resp = estimate(r["obs"], est_dir, cfg["pipeline"])
    t_est = time.time() - t0 - t_sim
    obs = Path(r["obs"])
    size = sum(f.stat().st_size for f in obs.rglob("*") if f.is_file())
    if not keep_frames:
        # not retained: drop frames and simulator truth (both regenerable from seed + config); the
        # observation logs (IMU, LED, timestamps, calib, meta) and metrics stay
        shutil.rmtree(obs / "rgb", ignore_errors=True)
        shutil.rmtree(obs / "depth", ignore_errors=True)
        shutil.rmtree(Path(r["truth"]), ignore_errors=True)
    return {"metrics": resp.get("metrics") if resp.get("ok") else None, "error": resp.get("error"),
            "manifest": r["manifest"], "t_sim_s": t_sim, "t_est_s": t_est, "bundle_bytes": size,
            "frames_kept": bool(keep_frames), "obs": r["obs"]}


class Evaluator:
    def __init__(self, cfg: dict, work_root=None, cache_root=None, n_workers: int | None = None,
                 log_path=None):
        from .aeromap import get_map
        self.cfg = cfg
        self.work_root = Path(work_root or DEFAULT_WORK)
        self.cache_root = Path(cache_root or DEFAULT_CACHE)
        self.n_workers = n_workers or max(1, (os.cpu_count() or 2) - 2)
        self.aero_version = get_map(cfg)[1]
        self.log_path = Path(log_path) if log_path else None
        self._pool = None
        self.counters = {"requests": 0, "unique_designs": 0, "scenario_evals": 0, "cache_hits": 0,
                         "simulated_drops": 0, "infeasible_geometry": 0}
        self._seen = set()

    def _get_pool(self):
        if self._pool is None and os.environ.get("CHUTESIM_REMOTE"):
            from .remote import RemotePool
            self._pool = RemotePool(os.environ["CHUTESIM_REMOTE"], self.cfg)
        if self._pool is None:
            os.environ.update(_ONE_THREAD)   # inherited by spawned workers (avoid BLAS/OpenMP oversubscription)
            ctx = mp.get_context("spawn")
            # inside MATLAB's out-of-process host sys.executable is not a Python interpreter
            ctx.set_executable(_python_exe())
            self._pool = ctx.Pool(self.n_workers)
        return self._pool

    def close(self):
        if self._pool is not None:
            self._pool.close()
            self._pool.join()
            self._pool = None

    def evaluate(self, designs: list, seeds: list[int], keep_frames: bool | None = None, mode: str = "fused",
                 tag: str = "eval") -> list[dict]:
        """designs: list of (q, slit_len, slit_r). Every design counts as one objective request."""
        cfg = self.cfg
        frac = cfg["retention"]["keep_frames_fraction"]
        run_root = self.work_root / f"{tag}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        results, tasks, slots = [], [], []
        for di, d in enumerate(designs):
            d = design_from(d)
            self.counters["requests"] += 1
            dk = canonical_json(design_key_part(d, cfg))
            if dk not in self._seen:
                self._seen.add(dk)
                self.counters["unique_designs"] += 1
            g = build_geometry(d, cfg)
            res = {"design": [d.q, d.slit_len, d.slit_r], "canonical": list(canonicalize(d, cfg).as_tuple()),
                   "radial": d.radial is not None,
                   "feasible": g.feasible, "per_scenario": [None] * len(seeds), "cache_hits": 0,
                   "simulated_drops": 0, "scenario_seeds": list(seeds)}
            results.append(res)
            if not g.feasible:
                self.counters["infeasible_geometry"] += 1
                res["objective"] = geometry_infeasible(g.reasons, cfg)
                continue
            for si, seed in enumerate(seeds):
                self.counters["scenario_evals"] += 1
                key, comp = cache_key(d, seed, cfg, self.aero_version)
                cp = _cache_path(self.cache_root, key)
                res.setdefault("cache_keys", []).append(key)
                if cp.exists():
                    with open(cp) as f:
                        res["per_scenario"][si] = json.load(f)["metrics"]
                    res["cache_hits"] += 1
                    self.counters["cache_hits"] += 1
                    continue
                keep = keep_frames if keep_frames is not None else (int(key[:8], 16) / 0xFFFFFFFF) < frac
                trial = f"d{di:04d}-s{seed}-{key[:8]}"
                dd = d.as_tuple() if d.radial is None else {"radial": list(d.radial), "slit_len": d.slit_len, "slit_r": d.slit_r}
                tasks.append((dd, int(seed), cfg, str(run_root), trial, keep))
                slots.append((di, si, key, comp))
        if tasks:
            remote = bool(os.environ.get("CHUTESIM_REMOTE"))
            outs = self._get_pool().map(_task, tasks, chunksize=1) if len(tasks) > 1 or self.n_workers > 1 or remote \
                else [_task(tasks[0])]
            for (di, si, key, comp), o in zip(slots, outs):
                results[di]["per_scenario"][si] = o["metrics"]
                results[di]["simulated_drops"] += 1
                results[di].setdefault("timing", []).append({"t_sim_s": o["t_sim_s"], "t_est_s": o["t_est_s"],
                                                             "bundle_bytes": o["bundle_bytes"]})
                self.counters["simulated_drops"] += 1
                if o["metrics"] is not None:  # pipeline errors are not cached
                    cp = _cache_path(self.cache_root, key)
                    cp.parent.mkdir(parents=True, exist_ok=True)
                    with open(cp, "w") as f:
                        json.dump({"key": key, "components": comp, "metrics": o["metrics"],
                                   "manifest": o["manifest"], "obs": o["obs"], "frames_kept": o["frames_kept"],
                                   "created": time.time()}, f, default=float)
                else:
                    results[di].setdefault("errors", []).append(o["error"])
        for r in results:
            if "objective" not in r:
                r["objective"] = score(r["per_scenario"], cfg, mode)
            r["evidence_level"] = "L2"
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a") as f:
                for r in results:
                    f.write(json.dumps({"t": time.time(), "tag": tag, "design": r["design"],
                                        "score": r["objective"]["score"], "status": r["objective"]["status"],
                                        "cache_hits": r["cache_hits"], "simulated_drops": r["simulated_drops"],
                                        "counters": dict(self.counters)}, default=float) + "\n")
        return results


def cache_audit(cfg: dict, cache_root=None) -> dict:
    """List cache entries whose components differ from the current configuration/code."""
    from .aeromap import get_map
    cur = component_hashes(cfg, get_map(cfg)[1])
    root = Path(cache_root or DEFAULT_CACHE)
    stale, ok = [], 0
    for p in root.rglob("*.json"):
        with open(p) as f:
            comp = json.load(f)["components"]
        diff = [k for k in cur if comp.get(k) != cur[k]]
        if diff:
            stale.append({"file": str(p), "outdated": diff})
        else:
            ok += 1
    return {"current": ok, "stale": stale, "environment": environment()}
