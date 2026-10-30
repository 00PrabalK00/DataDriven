"""Benchmark harness tests (ported from matlab/tests/testBench.m): budget cap, counted cache hits and
finite differences, counter consistency, every method on an analytic objective, hypervolume, summary
table, resume."""
import numpy as np
import pytest

from ddd.bench import COLUMNS, run_benchmark, summarize
from ddd.budget import BudgetedObjective, BudgetExhausted
from ddd.envs import analytic_env
from ddd.hv import hypervolume2d
from ddd.methods import METHODS, default_bounds, run_method

BUDGET = 30


def _out(n, score, drops=None, hits=None):
    return {"score": score, "secondary": np.zeros(n), "status": np.array(["ok"] * n, dtype=object),
            "drops": np.ones(n) if drops is None else drops, "cacheHits": np.zeros(n) if hits is None else hits,
            "meanSpeed": np.full(n, np.nan)}


@pytest.fixture(scope="module")
def runs():
    env = analytic_env("quadratic")
    return {m: run_method(m, env, BUDGET, 1000 * (i + 1) + 1) for i, m in enumerate(METHODS)}


def test_budget_cap_and_exhaustion():
    o = BudgetedObjective(analytic_env("quadratic"), 3)
    o.eval_vec(np.array([[4, 0.1, 0.4], [5, 0.1, 0.4], [6, 0.1, 0.4]]))
    with pytest.raises(BudgetExhausted):
        o.eval([4, 0.1, 0.4])
    assert o.requests == 3
    # a batch larger than the remaining budget: the part that fits is evaluated, then it raises
    o = BudgetedObjective(analytic_env("quadratic"), 200)
    lb, ub = default_bounds()
    with pytest.raises(BudgetExhausted):
        for _ in range(30):
            o.eval_vec(lb + np.random.default_rng(0).random((7, 3)) * (ub - lb))
    assert o.requests == 200 and len(o.F) == 200 and len(o.best_trace) == 200
    s = o.summary()
    assert s["bestAt"][3] == s["bestTrace"][199] and not np.isnan(s["bestAt"]).any()


def test_cached_requests_counted_and_counters_consistent():
    seen = set()

    def env(X):
        n = len(X)
        hits, drops = np.zeros(n), np.zeros(n)
        for i, x in enumerate(X):
            k = tuple(x)
            if k in seen:
                hits[i] = 1
            else:
                drops[i] = 1
                seen.add(k)
        return _out(n, X.sum(1), drops, hits)

    o = BudgetedObjective(env, 10)
    x = [4, 0.1, 0.4]
    o.eval_vec(np.array([x, x, x]))
    o.eval_vec(np.array([[4, 0, 0.3], [4, 0, 0.6]]))   # zero-slit: same canonical design
    s = o.summary()
    assert s["requests"] == 5
    assert s["uniqueDesigns"] == 2
    assert s["simulatedDrops"] + s["cacheHits"] == s["requests"]   # 1 scenario per request here
    assert s["cacheHits"] == 2


def test_finite_difference_calls_counted():
    calls = []

    def env(X):
        calls.append(len(X))
        return _out(len(X), (X ** 2).sum(1))

    r = run_method("gradient", env, 50, 2)
    assert r["requests"] == 50
    assert sum(calls) == 50          # every finite-difference evaluation is a counted request
    X = np.asarray(r["X"])
    d = np.diff(X, axis=0)
    h = 1e-2 * np.maximum(np.abs(X[:-1, 0]), 5.0)   # step v * max(|x|, TypicalX), TypicalX = midpoint
    fd = np.isclose(np.abs(d[:, 0]), h) & np.all(d[:, 1:] == 0, axis=1)
    assert fd.sum() >= 5                            # finite-difference points are among the requests


def test_every_method_runs_to_budget_and_improves(runs):
    lb, ub = default_bounds()
    X = lb + np.random.default_rng(7).random((500, 3)) * (ub - lb)
    random_median = np.median(analytic_env("quadratic")(X)["score"])
    for m, r in runs.items():
        assert r["requests"] <= BUDGET, m
        if not r["endedEarly"]:
            assert r["requests"] == BUDGET, m
            assert r["stopReason"] == "budget exhausted", m
        assert r["fbest"] < random_median, m
        assert np.all(np.diff(r["bestTrace"]) <= 0), m


def test_counters_consistent(runs):
    for m, r in runs.items():
        assert r["simulatedDrops"] == r["requests"], m        # analytic env: one drop per request
        assert r["requests"] >= r["uniqueDesigns"] >= 1, m
        assert len(r["X"]) == len(r["F"]) == len(r["bestTrace"]) == r["requests"], m
        assert 0 <= r["validGeometryRate"] <= 1 and r["sensingFailureRate"] == 0, m


def test_seeded_runs_reproducible():
    env = analytic_env("multimodal")
    for m in ("random", "ga", "sa", "pso", "tabu"):
        assert run_method(m, env, 25, 5)["F"] == run_method(m, env, 25, 5)["F"], m


def test_hypervolume_known_front():
    F = np.array([[1, 3], [2, 1], [3, 3.5]])          # (3, 3.5) is dominated
    hv, sp, front = hypervolume2d(F, [4, 4])
    assert hv == pytest.approx(3 * 1 + 2 * 2)
    assert front.shape == (2, 2) and np.isnan(sp)
    assert hypervolume2d(np.zeros((0, 2)), [1, 1])[0] == 0


def test_summarize_columns(runs):
    for r in runs.values():
        r["runIndex"] = 1
    T = summarize(list(runs.values()), BUDGET)
    assert [row["method"] for row in T] == list(METHODS)
    assert all(list(row) == COLUMNS for row in T)
    moo = next(row for row in T if row["method"] == "moo")
    assert moo["hypervolume_median"] > 0
    assert np.isnan(next(row for row in T if row["method"] == "ga")["hypervolume_median"])
    assert all(0 <= row["frac_reached_target"] <= 1 for row in T)


def test_benchmark_resume_skips_completed(tmp_path):
    kw = dict(methods=["random", "tabu"], n_runs=2, budget=20, out_dir=tmp_path, tag="l1", level="L1",
              env_name="analytic:quadratic", fresh_env_factory=lambda: analytic_env("quadratic"))
    B = run_benchmark(env_factory=lambda: analytic_env("quadratic"), **kw)
    assert len(B["table"]) == 2 and len(B["runs"]) == 4
    assert sorted(p.name for p in (tmp_path / "l1_runs").glob("*.json")) == \
        ["random_1.json", "random_2.json", "tabu_1.json", "tabu_2.json"]
    assert all("freshScore" in r for r in B["runs"])
    assert (tmp_path / "l1_summary.csv").exists() and (tmp_path / "l1_convergence.png").exists()

    def must_not_run():
        raise AssertionError("completed runs must be skipped")

    B2 = run_benchmark(env_factory=must_not_run, **kw)
    assert [r["F"] for r in B2["runs"]] == [r["F"] for r in B["runs"]]
    assert B2["runs"][1]["seed"] == 1002 and B2["runs"][2]["seed"] == 6001   # 1000*method_index + k
