"""Command line launcher for optimizer benchmarks.

    python -m ddd.cli_bench --env analytic --methods random ga --runs 10 --budget 200 --parallel 4 \
        --out results/benchmark_v2 --tag analytic_quadratic
"""
from __future__ import annotations

import argparse
import functools
import sys
from pathlib import Path

from .bench import ALL_METHODS, run_benchmark
from .envs import analytic_env, load_surrogate_model, simulator_env, surrogate_env


def _surrogate_factory(path, noise_sd, fail_prob):
    return surrogate_env(load_surrogate_model(path), noise_sd=noise_sd, fail_prob=fail_prob)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", choices=["analytic", "surrogate", "simulator"], required=True)
    ap.add_argument("--analytic-name", default="quadratic", help="quadratic | multimodal | edge")
    ap.add_argument("--surrogate-model", help="pickled callable / predict() model / {'score','secondary'} dict")
    ap.add_argument("--noise-sd", type=float, default=0.0, help="surrogate env: score noise")
    ap.add_argument("--fail-prob", type=float, default=0.0, help="surrogate env: sensing-failure probability")
    ap.add_argument("--methods", nargs="+", default=ALL_METHODS, choices=ALL_METHODS)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--run-indices", type=int, nargs="+", help="run only these run indices (default 1..runs)")
    ap.add_argument("--budget", type=int, default=200)
    ap.add_argument("--parallel", type=int, default=1, help="concurrent (method, run) jobs")
    ap.add_argument("--workers", type=int, help="simulator worker processes per env")
    ap.add_argument("--scenarios", type=int, default=5, help="simulator: fixed search scenarios")
    ap.add_argument("--fresh-scenarios", type=int, default=20, help="simulator: fresh re-score scenarios")
    ap.add_argument("--out", default="results/benchmark_v2")
    ap.add_argument("--tag", default="bench")
    ap.add_argument("--no-resume", action="store_true")
    a = ap.parse_args(argv)

    fresh = None
    if a.env == "analytic":
        factory = functools.partial(analytic_env, a.analytic_name)
        level, name = "L1", f"analytic:{a.analytic_name}"
    elif a.env == "surrogate":
        if not a.surrogate_model:
            ap.error("--surrogate-model is required for --env surrogate")
        factory = functools.partial(_surrogate_factory, a.surrogate_model, a.noise_sd, a.fail_prob)
        level, name = "L2", "surrogate environment (frozen; separate benchmark)"
    else:
        from chutesim.config import load_config
        cfg = load_config()
        o = cfg["objective"]
        seeds = [o["search_seed_base"] + i for i in range(a.scenarios)]
        fseeds = [o["fresh_seed_base"] + i for i in range(a.fresh_scenarios)]
        log = str(Path(a.out) / f"{a.tag}_requests.jsonl")
        factory = functools.partial(simulator_env, seeds, None, a.tag, log, a.workers)
        fresh = functools.partial(simulator_env, fseeds, None, f"{a.tag}-fresh", None, a.workers)
        level, name = "L2", f"simulator ({a.scenarios} fixed scenarios, common random numbers)"

    B = run_benchmark(a.methods, a.runs, a.budget, factory, fresh, a.out, a.tag, resume=not a.no_resume,
                      run_indices=a.run_indices, n_parallel=a.parallel, level=level, env_name=name)
    for row in B["table"]:
        print(f"{row['method']:9s} best_median={row['best_median']:.4g} iqr={row['best_iqr']:.3g} "
              f"evals_to_target={row['evals_to_target_median']:.4g} requests={row['requests_median']:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
