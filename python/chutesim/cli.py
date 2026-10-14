"""Command line: chutesim {drop,evaluate,pilot,cache-audit,compare}"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")


def _cfg(a):
    from .config import load_config
    return load_config(a.config)


def cmd_drop(a):
    from .evaluate import estimate
    from .geometry import Design
    from .run_drop import write_drop
    cfg = _cfg(a)
    t0 = time.time()
    r = write_drop(Design(a.q, a.slit_len, a.slit_r), a.seed, cfg, a.run_root, a.trial)
    t1 = time.time()
    resp = estimate(r["obs"], str(Path(a.run_root) / "est" / a.trial), cfg["pipeline"])
    print(json.dumps({"obs": r["obs"], "t_sim_s": t1 - t0, "t_est_s": time.time() - t1,
                      "ok": resp.get("ok"), "error": resp.get("error")}, indent=1))


def cmd_evaluate(a):
    from .evaluate import Evaluator
    cfg = _cfg(a)
    designs = json.loads(a.designs)
    seeds = list(range(cfg["objective"]["search_seed_base"], cfg["objective"]["search_seed_base"] + a.n_scenarios))
    ev = Evaluator(cfg, n_workers=a.workers, log_path=a.log)
    try:
        res = ev.evaluate(designs, seeds, tag="cli")
    finally:
        ev.close()
    for r in res:
        o = r["objective"]
        print(json.dumps({"design": r["design"], "score": o["score"], "status": o["status"],
                          "mean_preimpact_vz": o.get("mean_preimpact_vz"), "cache_hits": r["cache_hits"],
                          "simulated_drops": r["simulated_drops"], "evidence_level": r["evidence_level"]}))
    print(json.dumps(ev.counters))


def cmd_pilot(a):
    """Timing/storage pilot: N drops on the pool, then projections for the full benchmark."""
    import numpy as np
    from .evaluate import Evaluator
    cfg = _cfg(a)
    rng = np.random.default_rng(7)
    b = cfg["canopy"]["bounds"]
    designs = [(rng.uniform(*b["q"]), rng.uniform(*b["slit_len"]), rng.uniform(*b["slit_r"])) for _ in range(a.n_designs)]
    seeds = list(range(cfg["objective"]["search_seed_base"], cfg["objective"]["search_seed_base"] + a.n_scenarios))
    ev = Evaluator(cfg, n_workers=a.workers, cache_root=Path(a.cache) if a.cache else None)
    t0 = time.time()
    try:
        res = ev.evaluate(designs, seeds, keep_frames=False, tag="pilot")
    finally:
        ev.close()
    wall = time.time() - t0
    tim = [t for r in res for t in r.get("timing", [])]
    n = len(tim)
    status = [r["objective"]["status"] for r in res]
    sens = sum(len(r["objective"]["sensing_failures"]) for r in res)
    out = {
        "drops": n, "workers": ev.n_workers, "wall_s": wall, "drops_per_hour": n / wall * 3600 if wall else None,
        "t_sim_mean_s": float(np.mean([t["t_sim_s"] for t in tim])) if n else None,
        "t_est_mean_s": float(np.mean([t["t_est_s"] for t in tim])) if n else None,
        "bundle_mb_mean": float(np.mean([t["bundle_bytes"] for t in tim]) / 1e6) if n else None,
        "objective_status_counts": {s: status.count(s) for s in set(status)},
        "sensing_failure_scenarios": sens,
        "cpu_mhz_now": _cpu_mhz(),
    }
    full = 7 * 10 * 200 * cfg["objective"]["search_scenarios"]
    if n:
        out["projection_full_benchmark"] = {
            "simulated_drops_upper_bound": full,
            "hours_at_pilot_rate": full / out["drops_per_hour"],
            "transient_disk_gb_per_worker": out["bundle_mb_mean"] / 1e3,
            "retained_disk_gb_at_keep_fraction": full * cfg["retention"]["keep_frames_fraction"] * out["bundle_mb_mean"] / 1e3,
        }
    print(json.dumps(out, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1))


def _cpu_mhz():
    try:
        vals = [float(l.split(":")[1]) for l in open("/proc/cpuinfo") if l.startswith("cpu MHz")]
        return sum(vals) / len(vals)
    except Exception:
        return None


def cmd_audit(a):
    from .evaluate import cache_audit
    r = cache_audit(_cfg(a))
    print(json.dumps({"current": r["current"], "stale": len(r["stale"]), "examples": r["stale"][:5]}, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="chutesim")
    ap.add_argument("--config")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("drop")
    p.add_argument("--q", type=float, default=4.0)
    p.add_argument("--slit-len", type=float, default=0.15)
    p.add_argument("--slit-r", type=float, default=0.45)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--run-root", default="data/sim/manual")
    p.add_argument("--trial", default="t0001")
    p.set_defaults(f=cmd_drop)
    p = sp.add_parser("evaluate")
    p.add_argument("--designs", required=True, help='JSON list, e.g. "[[4,0.15,0.45]]"')
    p.add_argument("--n-scenarios", type=int, default=5)
    p.add_argument("--workers", type=int)
    p.add_argument("--log")
    p.set_defaults(f=cmd_evaluate)
    p = sp.add_parser("pilot")
    p.add_argument("--n-designs", type=int, default=10)
    p.add_argument("--n-scenarios", type=int, default=5)
    p.add_argument("--workers", type=int)
    p.add_argument("--cache", help="separate cache dir for the pilot")
    p.add_argument("--out")
    p.set_defaults(f=cmd_pilot)
    p = sp.add_parser("cache-audit")
    p.set_defaults(f=cmd_audit)
    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
