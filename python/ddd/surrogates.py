"""Surrogate models on feature matrices + leave-geometry-out cross-validation.

Port of matlab/+chute/+surrogate/{fitModels, leaveGeometryOutCV}.m:
  linear     ordinary least squares (fitlm 'linear')
  quadratic  full quadratic incl. interactions (fitlm 'quadratic')
  gp         Gaussian process, ARD Matern 5/2 + noise, standardised inputs/outputs
             (MATLAB m10 used ARD squared-exponential; v2 uses ARD Matern 5/2 as in bayesopt)
  ensemble   bagged regression trees = random forest with 100 trees (fitrensemble 'Bag')
CV: all rows of one geometry are held out together, so accuracy refers to unseen designs.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

MODEL_NAMES = ("linear", "quadratic", "gp", "ensemble")


def make_model(name: str, seed: int = 0, gp_restarts: int = 1):
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import PolynomialFeatures, StandardScaler
    if name == "linear":
        return LinearRegression()
    if name == "quadratic":
        return make_pipeline(StandardScaler(), PolynomialFeatures(2), LinearRegression())
    if name == "gp":
        return _GPModel(seed, gp_restarts)
    if name == "ensemble":
        return RandomForestRegressor(n_estimators=100, random_state=seed, n_jobs=-1)
    if name == "boosting":
        return GradientBoostingRegressor(random_state=seed)
    raise ValueError(f"unknown surrogate {name!r}")


class _GPModel:
    """GP with ARD Matern 5/2 + white noise on standardised X, normalised y."""

    def __init__(self, seed=0, restarts=2):
        self.seed, self.restarts = seed, restarts

    def fit(self, X, y):
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
        X = np.asarray(X, float)
        self.mx, self.sx = X.mean(0), X.std(0) + 1e-12
        d = X.shape[1]
        k = ConstantKernel(1.0, (1e-3, 1e3)) * Matern(np.ones(d), (1e-2, 1e3), nu=2.5) + WhiteKernel(1e-2, (1e-8, 1e1))
        self.gp = GaussianProcessRegressor(k, normalize_y=True, n_restarts_optimizer=self.restarts,
                                           random_state=self.seed)
        import warnings

        from sklearn.exceptions import ConvergenceWarning
        with warnings.catch_warnings():   # length scale at its upper bound = inert input; expected
            warnings.simplefilter("ignore", ConvergenceWarning)
            self.gp.fit((X - self.mx) / self.sx, np.asarray(y, float))
        return self

    def predict(self, X, return_std=False):
        Z = (np.asarray(X, float) - self.mx) / self.sx
        return self.gp.predict(Z, return_std=return_std)


def fit_models(X, y, names=MODEL_NAMES, seed: int = 0) -> dict:
    return {n: make_model(n, seed).fit(np.asarray(X, float), np.asarray(y, float)) for n in names}


def predict(model, X):
    return np.asarray(model.predict(np.atleast_2d(np.asarray(X, float))), float)


def group_folds(groups, n_folds: int | None = None, seed: int = 0) -> np.ndarray:
    """Fold index per row: unique groups shuffled, then dealt round-robin (as leaveGeometryOutCV.m)."""
    u, inv = np.unique(np.asarray(groups), return_inverse=True)
    n_folds = len(u) if n_folds is None else n_folds
    fold_u = np.empty(len(u), int)
    fold_u[np.random.default_rng(seed).permutation(len(u))] = np.arange(len(u)) % n_folds
    return fold_u[inv]


def leave_geometry_out_cv(X, y, groups, names=MODEL_NAMES, n_folds: int | None = None, seed: int = 0):
    """Returns (table rows [{model, rmse, mae, rank_corr}], out-of-fold predictions (n, n_models))."""
    X = np.asarray(X, float); y = np.asarray(y, float)
    fold = group_folds(groups, n_folds, seed)
    pred = np.full((len(y), len(names)), np.nan)
    for f in np.unique(fold):
        te = fold == f
        M = fit_models(X[~te], y[~te], names, seed)
        for j, n in enumerate(names):
            pred[te, j] = predict(M[n], X[te])
    rows = []
    for j, n in enumerate(names):
        ok = np.isfinite(pred[:, j])
        e = pred[ok, j] - y[ok]
        rows.append({"model": n, "rmse": float(np.sqrt(np.mean(e**2))), "mae": float(np.mean(np.abs(e))),
                     "rank_corr": float(spearmanr(pred[ok, j], y[ok]).statistic)})
    return rows, pred


def save_model(model, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(model, f)


def load_model(path):
    with open(path, "rb") as f:
        return pickle.load(f)
