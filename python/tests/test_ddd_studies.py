"""Tests for the Python port of the representation / surrogate / sensitivity / DOE studies (ddd)."""
import numpy as np
import pytest

from ddd import doe, flight, latent, rep, sensitivity, surrogates


@pytest.fixture(scope="module")
def shapes():
    R, info = rep.shape_dataset(400, 2)
    return R[info["valid"]], info


def test_shape_dataset_area_and_validity():
    R, info = rep.shape_dataset(200, 1)
    assert np.max(np.abs(rep.polar_area(R) - np.pi)) < 1e-9
    assert info["valid"].mean() > 0.7
    assert set(info["family"]) == {"superellipse", "fourier", "rounded_polygon"}


def test_pca_variance_monotone(shapes):
    R, _ = shapes
    T = rep.pca_study(R, (2, 4, 8))["table"]
    var = [r["var_retained_pct"] for r in T]; rmse = [r["recon_rmse"] for r in T]
    assert var == sorted(var) and rmse == sorted(rmse, reverse=True)
    P = rep.fit_pca(R)
    assert np.all(np.diff(P.explained) <= 1e-9) and abs(P.explained.sum() - 100) < 1e-9


def test_ae_beats_mean_shape(shapes):
    R, _ = shapes
    A = rep.ae_study(R, (4,), epochs=40, n_jobs=1)
    row = A["table"][0]
    assert row["test_recon_rmse"] < 0.7 * row["mean_shape_rmse"]
    assert row["valid_rate"] > 0.8


def test_model_save_load_roundtrip(shapes, tmp_path):
    R, _ = shapes
    P = rep.fit_pca(R)
    ae = rep.train_ae(R, 3, epochs=2)
    V = rep.train_vae(R, 2, epochs=2)
    rep.save_models(tmp_path, P, {3: ae}, V)
    M = rep.load_models(tmp_path)
    Z = np.random.default_rng(0).standard_normal((5, 3)) * 0.1
    assert np.allclose(M["ae"][3].decode(Z), ae.decode(Z))
    assert np.allclose(M["vae"].decode(Z[:, :2]), V.decode(Z[:, :2]))
    assert np.allclose(M["pca"].decode(Z), P.decode(Z))


def test_latent_decode_250cm2(shapes, cfg):
    R, _ = shapes
    P = rep.fit_pca(R)
    V = rep.train_vae(R, 4, epochs=30)
    reps = latent.make_representations(R, P, None, V, k=4, cfg=cfg)
    rng = np.random.default_rng(0)
    for name in ("pca", "vae", "param3"):
        r = reps[name]
        X = r.lb + rng.random((20, r.dim)) * (r.ub - r.lb)
        if name != "param3":
            X[:, r.k] = rng.uniform(0.05, 0.15, 20); X[:, r.k + 1] = rng.uniform(0.40, 0.50, 20)
        D = r.decode(X)
        if name != "param3":
            assert set(D[0]) == {"radial", "slit_len", "slit_r"} and len(D[0]["radial"]) == 64
            assert np.allclose(rep.polar_area(np.array([d["radial"] for d in D])), np.pi)
        chk = latent.check_designs(D, cfg)
        assert all(abs(c["area_cm2"] - 250.0) < 1e-6 for c in chk)
        assert np.mean([c["feasible"] for c in chk]) >= 0.6, (name, chk)
    seen = []
    env = latent.latent_env(reps["pca"], lambda designs: seen.extend(designs) or len(designs))
    assert env(np.tile((reps["pca"].lb + reps["pca"].ub) / 2, (3, 1))) == 3 and len(seen) == 3


def test_sobol_ishigami():
    S = sensitivity.sobol_indices(sensitivity.ishigami, [-np.pi] * 3, [np.pi] * 3, 20000, seed=0)
    assert np.allclose(S["first"], [0.314, 0.442, 0.0], atol=0.05)
    assert np.allclose(S["total"], [0.558, 0.442, 0.244], atol=0.05)


def test_sobol_large_offset():
    f = lambda X: 6.85 + 0.01 * (X[:, 0] + 2 * X[:, 1])  # noqa: E731
    S = sensitivity.sobol_indices(f, [0, 0, 0], [1, 1, 1], 20000)
    assert np.allclose(S["first"], [0.2, 0.8, 0.0], atol=0.05) and S["total"][2] < 0.02


def test_lhs_bounds_and_baselines(cfg):
    D, info = doe.lhs_designs(16, 1, cfg=cfg)
    lb, ub = doe.bounds(cfg)
    assert D.shape == (18, 3)
    assert np.all(D >= lb - 1e-12) and np.all(D <= ub + 1e-12)
    assert np.array_equal(D[info["is_baseline"]], [[2, 0, 0.45], [4, 0, 0.45]])
    assert doe.is_feasible(D, cfg)[0].all()


def test_schedule_randomised(cfg):
    D, info = doe.lhs_designs(16, 1, cfg=cfg)
    T = doe.drop_schedule(D, info["is_baseline"], 3, 5)
    assert len(T) == 54
    for b in (1, 2, 3):
        assert sorted(r["design"] for r in T if r["repeat"] == b) == list(range(1, 19))
    assert [r["design"] for r in T[:18]] != list(range(1, 19))
    assert sum(r["baseline"] for r in T) == 6
    T2 = doe.drop_schedule(D, info["is_baseline"], 3, 6)
    assert [r["design"] for r in T] != [r["design"] for r in T2]


def test_discrepancy_prefers_spread():
    from scipy.stats import qmc
    good = doe.maximin_lhs(30, 3, 0)
    bad = 0.5 + 0.1 * np.random.default_rng(0).random((30, 3))
    assert doe.centered_l2_discrepancy(good) < doe.centered_l2_discrepancy(bad)
    assert np.isclose(doe.centered_l2_discrepancy(good) ** 2, qmc.discrepancy(good, method="CD"))


def test_surrogate_cv_runs(tmp_path):
    rng = np.random.default_rng(1)
    X = rng.random((60, 3)); g = np.repeat(np.arange(20), 3); y = X[:, 0] ** 2 + 0.01 * rng.standard_normal(60)
    rows, pred = surrogates.leave_geometry_out_cv(X, y, g, surrogates.MODEL_NAMES, 5)
    r = {x["model"]: x for x in rows}
    assert r["quadratic"]["rmse"] < r["linear"]["rmse"]
    assert r["gp"]["rank_corr"] > 0.9 and np.isfinite(pred).all()
    # folds keep each geometry together
    f = surrogates.group_folds(g, 5)
    assert all(len(set(f[g == k])) == 1 for k in range(20))
    M = surrogates.fit_models(X, y, ["gp"])["gp"]
    surrogates.save_model(M, tmp_path / "gp.pkl")
    assert np.allclose(surrogates.load_model(tmp_path / "gp.pkl").predict(X[:5]), M.predict(X[:5]))


def test_flight_clusters_separates_blobs():
    rng = np.random.default_rng(0)
    F = np.vstack([rng.normal(c, 0.2, (60, 7)) for c in (0.0, 2.0, 4.0)])
    K = flight.flight_clusters(F, k_range=range(2, 5), n_init=5)
    assert K["k"] == 3 and K["meaningful"] and sum(c["n"] for c in K["centroids"]) == 180
