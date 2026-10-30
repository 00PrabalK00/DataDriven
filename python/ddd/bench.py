"""Optimizer benchmark (port of matlab/+chute/+bench/runBenchmark.m, summarize.m, convergencePlot.m).

Same encoding, bounds, environment and maximum budget for every method; n_runs independent runs
each; best-so-far at 25/50/100/200; three counters; each run's best design re-scored on fresh
scenarios. Outputs one checkpoint JSON per run, a summary CSV and a convergence plot (median + IQR),
tagged with the evidence level.
"""
from __future__ import annotations

import csv
import json
import os
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from .hv import hypervolume2d
from .methods import METHODS, run_method

ALL_METHODS = list(METHODS)   # run seed = 1000 * (index in this list, 1-based) + k
EVIDENCE = {"L1": "L1 software validation (synthetic truth)",
            "L2": "L2 synthetic benchmark under assumed aerodynamics",
            "L3": "L3 calibrated-model prediction",
            "L4": "L4 physical demonstration"}
COLUMNS = ["method", "runs", "best_median", "best_iqr", "best_at25", "best_at50", "best_at100", "best_at200",
           "evals_to_target_median", "frac_reached_target", "requests_median", "unique_designs_median",
           "simulated_drops_median", "valid_geometry_rate", "sensing_failure_rate", "wall_s_median",
           "frac_ended_early", "fresh_score_median", "hypervolume_median", "spacing_median"]
# fixed colour per method (validated categorical palette, fixed order: colour follows the method)
COLORS = dict(zip(ALL_METHODS, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300",
                                "#6250d6", "#e34948"]))


def run_seed(method: str, k: int) -> int:
    return 1000 * (ALL_METHODS.index(method) + 1) + int(k)


def _write_json(path: Path, obj):
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    with open(tmp, "w") as f:
        json.dump(obj, f, default=_json_default)
    os.replace(tmp, path)


def _json_default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(type(o))


def _run_one(method, k, budget, env_factory, settings, path, env=None):
    own = env is None
    env = env_factory() if own else env
    try:
        r = run_method(method, env, budget, run_seed(method, k), bounds=getattr(env, "bounds", None),
                       settings=(settings or {}).get(method))
    finally:
        if own and hasattr(env, "close"):
            env.close()
    r["runIndex"] = int(k)
    _write_json(Path(path), r)
    return r


def load_runs(runs_dir: Path, methods=None) -> list[dict]:
    runs = []
    for p in sorted(Path(runs_dir).glob("*.json")):
        with open(p) as f:
            r = json.load(f)
        if methods is None or r["method"] in methods:
            r["_path"] = str(p)
            runs.append(r)
    runs.sort(key=lambda r: (ALL_METHODS.index(r["method"]), r["runIndex"]))
    return runs


def run_benchmark(methods, n_runs: int = 10, budget: int = 200, env_factory=None, fresh_env_factory=None,
                  out_dir="results/benchmark_v2", tag: str = "bench", resume: bool = True, run_indices=None,
                  n_parallel: int = 1, level: str | None = None, env_name: str = "", settings: dict | None = None,
                  rescore: bool = True, plot: bool = True) -> dict:
    """settings: optional {method: settings dict}. Returns {runs, table, level, envName}."""
    out = Path(out_dir)
    runs_dir = out / f"{tag}_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    ks = list(run_indices) if run_indices is not None else list(range(1, n_runs + 1))
    todo = []
    for m in methods:
        if m not in ALL_METHODS:
            raise ValueError(f"unknown method {m}")
        for k in ks:
            p = runs_dir / f"{m}_{k}.json"
            if resume and p.exists():
                continue
            todo.append((m, k, p))
    n_done = len(methods) * len(ks) - len(todo)
    if n_done:
        print(f"resuming: {n_done} completed runs found in {runs_dir}", flush=True)
    total = len(methods) * len(ks)
    stamp = lambda: time.strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
    if n_parallel > 1 and len(todo) > 1:
        with ProcessPoolExecutor(max_workers=n_parallel) as ex:
            futs = {ex.submit(_run_one, m, k, budget, env_factory, settings, str(p)): (m, k) for m, k, p in todo}
            for fut in as_completed(futs):
                fut.result()
                m, k = futs[fut]
                n_done += 1
                print(f"[{stamp()}] {m} run {k} done ({n_done}/{total})", flush=True)
                _write_progress(out, tag, runs_dir, methods, total)
    elif todo:
        env = env_factory()
        try:
            for m, k, p in todo:
                print(f"[{stamp()}] {m} run {k}/{n_runs}", flush=True)
                _run_one(m, k, budget, env_factory, settings, str(p), env=env)
                _write_progress(out, tag, runs_dir, methods, total)
        finally:
            if hasattr(env, "close"):
                env.close()
    runs = load_runs(runs_dir, methods)
    # fresh-scenario re-scoring of each run's best design
    if rescore and fresh_env_factory is not None:
        need = [r for r in runs if "freshScore" not in r and r["xbest"]]
        if need:
            fenv = fresh_env_factory()
            try:
                Xu, iu = np.unique(np.array([r["xbest"] for r in need], float), axis=0, return_inverse=True)
                rr = fenv(Xu)
            finally:
                if hasattr(fenv, "close"):
                    fenv.close()
            for r, i in zip(need, np.ravel(iu)):
                r["freshScore"] = float(rr["score"][i])
                r["freshStatus"] = str(rr["status"][i])
                r["freshSpeed"] = float(rr["meanSpeed"][i])
                _write_json(Path(r["_path"]), {k: v for k, v in r.items() if k != "_path"})
    level = level or getattr(env_factory, "level", None) or "L1"
    table = summarize(runs, budget)
    write_csv(table, out / f"{tag}_summary.csv")
    if plot and runs:
        convergence_plot(runs, budget, out / f"{tag}_convergence.png", f"{EVIDENCE.get(level, level)} | {env_name}")
    _write_json(out / f"{tag}_benchmark.json", {"tag": tag, "level": level, "envName": env_name,
                                                 "budget": budget, "methods": list(methods), "table": table})
    return {"runs": runs, "table": table, "level": level, "envName": env_name}


def _write_progress(out, tag, runs_dir, methods, total):
    runs = load_runs(runs_dir, methods)
    _write_json(out / f"{tag}_progress.json", {
        "tag": tag, "completed_runs": len(runs), "total_runs": total,
        "simulated_drops": int(sum(r["simulatedDrops"] for r in runs)),
        "requests": int(sum(r["requests"] for r in runs)), "updated": time.strftime("%Y-%m-%d %H:%M:%S")})


# ------------------------------------------------------------------------------------- summary
def _prctile(a, q):
    """MATLAB prctile (midpoint / 'hazen' interpolation), NaNs ignored."""
    return np.nanpercentile(a, q, method="hazen", axis=0)


def _nanmedian(a):
    a = np.asarray(a, float)
    return float(np.median(a[~np.isnan(a)])) if np.any(~np.isnan(a)) else np.nan


def _first_hit(trace, target):
    idx = np.nonzero(np.asarray(trace) <= target)[0]
    return float(idx[0] + 1) if idx.size else np.nan


def summarize(runs: list[dict], budget: int = 200) -> list[dict]:
    """Per-method table: median/IQR best at checkpoints, evaluations to reach a target, counters,
    failure rates, runtime, fresh re-score, hypervolume/spacing (moo)."""
    if not runs:
        return []
    # target: within 10% of the gap between a typical valid design (median of all valid evaluations)
    # and the best value any run found
    f_all = min(r["fbest"] for r in runs)
    ok_f = np.concatenate([np.asarray(r["F"], float)[np.asarray(r["status"]) == "ok"] for r in runs])
    target = f_all + 0.1 * (np.median(ok_f) - f_all) if ok_f.size else np.nan
    # multi-objective quality: hypervolume / spacing of each run's non-dominated set (valid points only)
    moo = [r for r in runs if r["method"] == "moo"]
    ref = np.array([np.nan, np.nan])
    if moo:
        P = np.concatenate([np.column_stack([r["F"], r["F2"]])[np.asarray(r["status"]) == "ok"] for r in moo])
        if P.size:
            ref = P.max(axis=0) * 1.05

    def hv(r, i):
        if r["method"] != "moo" or np.any(np.isnan(ref)):
            return np.nan
        ok = np.asarray(r["status"]) == "ok"
        return hypervolume2d(np.column_stack([r["F"], r["F2"]])[ok], ref)[i]

    rows = []
    for m in dict.fromkeys(r["method"] for r in runs):
        R = [r for r in runs if r["method"] == m]
        fb = np.array([r["fbest"] for r in R], float)
        best_at = np.array([r["bestAt"] for r in R], float)
        e2t = np.array([_first_hit(r["bestTrace"], target) for r in R])
        q = np.percentile(fb, [25, 75], method="hazen")
        rows.append(dict(zip(COLUMNS, [
            m, len(R), float(np.median(fb)), float(q[1] - q[0]),
            *[_nanmedian(best_at[:, j]) for j in range(4)],
            _nanmedian(e2t), float(np.mean(~np.isnan(e2t))),
            float(np.median([r["requests"] for r in R])), float(np.median([r["uniqueDesigns"] for r in R])),
            float(np.median([r["simulatedDrops"] for r in R])),
            float(np.mean([r["validGeometryRate"] for r in R])), float(np.mean([r["sensingFailureRate"] for r in R])),
            float(np.median([r["wall_s"] for r in R])), float(np.mean([r["endedEarly"] for r in R])),
            _nanmedian([r.get("freshScore", np.nan) for r in R]),
            _nanmedian([hv(r, 0) for r in R]), _nanmedian([hv(r, 1) for r in R])])))
    return rows


def write_csv(table: list[dict], path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for row in table:
            w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in row.items()})


# ------------------------------------------------------------------------------- convergence plot
def convergence_plot(runs: list[dict], budget: int, path, subtitle: str = ""):
    """Best-so-far vs objective requests: median line and IQR band per method. The y-range is set
    from the 1st-99th percentile of all trace values so a single penalty value cannot stretch it."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ink, ink2, grid = "#0b0b0b", "#52514e", "#e4e3df"
    plt.rcParams.update({"font.size": 11, "axes.edgecolor": ink2, "axes.labelcolor": ink, "xtick.color": ink2,
                         "ytick.color": ink2, "font.family": "DejaVu Sans"})
    fig, ax = plt.subplots(figsize=(9, 5.2), facecolor="white")
    x = np.arange(1, budget + 1)
    allv = []
    for m in dict.fromkeys(r["method"] for r in runs):
        R = [r for r in runs if r["method"] == m]
        M = np.full((len(R), budget), np.nan)
        for i, r in enumerate(R):
            t = np.asarray(r["bestTrace"], float)[:budget]
            M[i, :t.size] = t
            if 0 < t.size < budget:
                M[i, t.size:] = t[-1]   # converged early: hold final value
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            q = _prctile(M, [25, 50, 75])
        ok = ~np.isnan(q[1])
        c = COLORS.get(m, ink2)
        ax.fill_between(x[ok], q[0, ok], q[2, ok], color=c, alpha=0.15, linewidth=0)
        ax.plot(x[ok], q[1, ok], color=c, linewidth=2, label=m)
        allv.append(M[np.isfinite(M)])
    v = np.concatenate(allv) if allv else np.array([])
    if v.size:
        lo, hi = np.percentile(v, [1, 99])
        pad = 0.05 * (hi - lo) if hi > lo else max(abs(hi), 1.0) * 0.05
        ax.set_ylim(lo - pad, hi + pad)
    for cp in (25, 50, 100, 200):
        if cp <= budget:
            ax.axvline(cp, color=grid, linewidth=1, linestyle=":", zorder=0)
    ax.set_xlim(1, budget)
    ax.grid(axis="y", color=grid, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_xlabel("objective requests (cached evaluations included)")
    ax.set_ylabel("best score so far (lower = slower landing)")
    ax.set_title("Optimizer convergence (median, IQR band)", loc="left", fontsize=13, color=ink, pad=22)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9.5, color=ink2)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
