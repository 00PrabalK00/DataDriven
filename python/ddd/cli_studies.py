"""Studies of milestone 10 in Python (port of matlab/scripts/m10_studies.m, without the latent search,
which needs simulations and lives in the benchmark runner).

  python -m ddd.cli_studies --what rep|surrogate|sobol|flight|all --out results/studies_v2

rep        shape dataset (3000, seed 1) -> PCA / AE / VAE tables, saved models, figures
flight     per-drop flight features from the evaluation cache -> PCA + k-means centroids, figure
surrogate  leave-geometry-out CV of linear/quadratic/GP/ensemble on a data CSV (features + target)
sobol      GP on the same data -> Sobol first/total indices + response maps
Default data CSV for surrogate/sobol: scenario-averaged preimpact_vz per design (q, slit_len, slit_r) from
the flight features, at most 1500 designs (as m10_studies.m). Evidence level of all results: L2.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from chutesim.config import REPO_ROOT

from . import flight, rep, sensitivity, surrogates
from .latent import param3_bounds

L2 = "L2: simulation (prior-v1 aero map + virtual sensors + shared pipeline), not calibrated to real drops"
# reference categorical palette (dataviz skill), first slots
C_BLUE, C_ORANGE, C_AQUA, C_VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.dpi": 150, "savefig.dpi": 150, "font.size": 10, "axes.titlesize": 11,
                         "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.color": GRID, "grid.linewidth": 0.6, "legend.frameon": False,
                         "figure.facecolor": "white", "axes.facecolor": "white"})
    return plt


def _footer(fig, text=L2):
    eng = fig.get_layout_engine()
    if eng is not None and hasattr(eng, "set"):
        eng.set(rect=(0, 0.045, 1, 0.955))      # keep the footnote clear of axes labels
    fig.text(0.01, 0.008, text, fontsize=7, color=INK2, ha="left", va="bottom")


def _xy(r):
    th = rep.theta(len(r))
    t = np.r_[th, th[0]]; rr = np.r_[r, r[0]]
    return rr * np.cos(t), rr * np.sin(t)


def _write(path, rows):
    flight.write_csv(path, rows)
    print(f"wrote {path}")


def plot_reconstructions(figs, R, fam, te, Pm, ae4):
    """Held-out outlines vs PCA / AE (k = 4) reconstructions, two per family."""
    plt = _plt()
    Rte = R[te]; fte = fam[te]
    pick = []
    for f in ("superellipse", "fourier", "rounded_polygon"):
        pick += list(np.flatnonzero(fte == f)[[0, -1]])
    Rp = Pm.decode(Pm.encode(Rte[pick], 4)); Ra = ae4.decode(ae4.encode(Rte[pick]))
    fig, axes = plt.subplots(1, len(pick), figsize=(2.0 * len(pick), 2.7), constrained_layout=True)
    for j, (ax, i) in enumerate(zip(axes, pick)):
        ax.plot(*_xy(Rte[i]), color=INK, lw=2.2, label="original")
        ax.plot(*_xy(Rp[j]), color=C_BLUE, lw=1.4, ls="--", label="PCA k=4")
        ax.plot(*_xy(Ra[j]), color=C_ORANGE, lw=1.4, label="AE k=4")
        ax.set_xlim(-1.45, 1.45); ax.set_ylim(-1.45, 1.45)
        ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(fte[i].replace("_", " "), fontsize=8, color=INK2)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="outside lower center", ncol=3, fontsize=8)
    fig.suptitle("Held-out outlines and their 4-number reconstructions", fontsize=11)
    fig.savefig(figs / "reconstruction_examples.png"); plt.close(fig)


# ---------------------------------------------------------------- rep
def run_rep(out: Path, epochs: int = 150, n: int = 3000):
    figs = out / "figures"; figs.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    R, info = rep.shape_dataset(n, 1)
    print(f"dataset: {n} shapes, valid {info['valid'].mean():.3f}")
    fam = info["family"][info["valid"]]
    R = R[info["valid"]]
    P = rep.pca_study(R)
    _write(out / "rep_pca.csv", P["table"])
    A = rep.ae_study(R, (2, 3, 4, 6, 8), epochs=epochs)
    _write(out / "rep_ae.csv", A["table"])
    V = rep.vae_study(R, 4, epochs=epochs)
    line = (f"VAE k=4: generated valid rate {V['valid_rate']:.3f}, diversity {V['diversity']:.3f} "
            f"(data {V['data_diversity']:.3f})\n")
    (out / "rep_vae.txt").write_text(line); print(line.strip())
    (out / "rep_vae.json").write_text(json.dumps({k: V[k] for k in ("valid_rate", "diversity", "data_diversity")}))
    rep.save_models(out / "models", P["model"], A["models"], V["model"])
    np.savez(out / "models" / "shapes.npz", R=R, family=fam, test_mask=A["test_mask"])
    print(f"rep done in {time.time() - t0:.0f} s")

    plt = _plt()
    # PCA variance curve
    Pm = P["model"]
    cum = np.cumsum(Pm.explained)[:16]
    ks = np.arange(1, len(cum) + 1)
    fig, ax = plt.subplots(figsize=(6.4, 4.0), constrained_layout=True)
    ax.bar(ks, Pm.explained[:16], color=C_BLUE, alpha=0.35, width=0.7, label="per component")
    ax.plot(ks, cum, "-o", color=C_BLUE, lw=2, ms=5, label="cumulative")
    k4 = cum[3]
    ax.axhline(90, color=INK2, lw=0.8, ls="--")
    ax.annotate(f"k = 4: {k4:.1f}%", (4, k4), xytext=(6.2, k4 - 14), color=INK,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.text(15.8, 91, "90%", ha="right", va="bottom", color=INK2, fontsize=8)
    ax.set_xlabel("number of principal components k"); ax.set_ylabel("variance explained (%)")
    ax.set_title(f"PCA of {len(R)} area-normalised outlines r(θ) (64 samples)")
    ax.set_xticks(ks); ax.set_ylim(0, 102); ax.legend(loc="center right")
    _footer(fig, "Geometry-only dataset: superellipses, Fourier-perturbed circles, rounded polygons")
    fig.savefig(figs / "pca_variance.png"); plt.close(fig)

    plot_reconstructions(figs, R, fam, A["test_mask"], Pm, A["models"][4])

    # reconstruction error vs k: PCA vs AE
    fig, ax = plt.subplots(figsize=(5.6, 3.8), constrained_layout=True)
    ax.plot([r["k"] for r in P["table"]], [r["recon_rmse"] for r in P["table"]], "-o", color=C_BLUE, lw=2, label="PCA (all shapes)")
    ax.plot([r["k"] for r in A["table"]], [r["test_recon_rmse"] for r in A["table"]], "-s", color=C_ORANGE, lw=2, label="autoencoder (test split)")
    ax.axhline(A["table"][0]["mean_shape_rmse"], color=INK2, ls="--", lw=0.8)
    ax.text(12, A["table"][0]["mean_shape_rmse"], "mean shape", color=INK2, fontsize=8, ha="right", va="bottom")
    ax.set_xlabel("latent size k"); ax.set_ylabel("reconstruction RMSE (units of R_eq)")
    ax.set_ylim(0, None); ax.set_title("Reconstruction error vs latent size"); ax.legend()
    fig.savefig(figs / "reconstruction_rmse.png"); plt.close(fig)

    # VAE generated grid
    G = V["generated"]; ok = rep.is_valid_shape(G)
    fig, axes = plt.subplots(4, 8, figsize=(12, 6.4), constrained_layout=True)
    for ax, g, v in zip(axes.ravel(), G[:32], ok[:32]):
        x, y = _xy(g)
        ax.fill(x, y, color=C_VIOLET if v else C_ORANGE, alpha=0.18)
        ax.plot(x, y, color=C_VIOLET if v else C_ORANGE, lw=1.4)
        ax.set_xlim(-1.6, 1.6); ax.set_ylim(-1.6, 1.6); ax.set_aspect("equal"); ax.axis("off")
    fig.suptitle(f"VAE (k = 4): 32 outlines sampled from the prior N(0, I), all scaled to 250 cm²\n"
                 f"valid {V['valid_rate'] * 100:.0f}% of 500 samples; diversity {V['diversity']:.2f} vs data {V['data_diversity']:.2f} "
                 f"(mean pairwise distance)", fontsize=11)
    fig.savefig(figs / "vae_samples.png"); plt.close(fig)
    return {"pca": P["table"], "ae": A["table"], "vae": line.strip()}


# ---------------------------------------------------------------- flight
def flight_table(out: Path, rebuild: bool = False, cache_root: str = ""):
    f = out / "flight_features.csv"
    if rebuild or not f.exists():
        n = flight.build_flight_features(f, cache_root)
        print(f"flight features: {n} drops -> {f}")
    return flight.complete_rows(flight.read_csv(f))


def run_flight(out: Path, rebuild: bool = False, cache_root: str = ""):
    figs = out / "figures"; figs.mkdir(parents=True, exist_ok=True)
    T = flight_table(out, rebuild, cache_root)
    print(f"{len(T['q'])} drops with complete sensor-derived features")
    F = np.column_stack([T[k] for k in flight.FEATURES])
    rng = np.random.default_rng(0)
    if len(F) > 3000:
        F = F[rng.permutation(len(F))[:3000]]
    K = flight.flight_clusters(F)
    _write(out / "flight_clusters.csv", K["centroids"])
    summ = {"k": K["k"], "best_silhouette_sqeuclidean": K["best_silhouette"],
            "silhouette_sqeuclidean": K["silhouette"], "silhouette_euclidean": K["silhouette_euclidean"],
            "meaningful": bool(K["meaningful"]), "pca_explained_pct": K["pca"]["explained"].tolist(),
            "pca_n_for_90": K["pca"]["n_for_90"], "n_drops_used": len(F)}
    (out / "flight_kmeans.json").write_text(json.dumps(summ, indent=1))
    print(f"k-means: k={K['k']} silhouette {K['best_silhouette']:.2f} (sq. Euclidean, as MATLAB; Euclidean "
          f"{K['silhouette_euclidean'][K['k']]:.2f}) meaningful={K['meaningful']}; PCA needs {K['pca']['n_for_90']} comps for 90%")

    plt = _plt()
    cols = [C_BLUE, C_ORANGE, C_AQUA, C_VIOLET, "#eda100", "#008300"]
    S = K["pca"]["score"]; ex = K["pca"]["explained"]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 4.4), constrained_layout=True, gridspec_kw={"width_ratios": [1.4, 1]})
    for c in range(K["k"]):
        m = K["labels"] == c
        cen = K["centroids"][c]
        ax.scatter(S[m, 0], S[m, 1], s=9, color=cols[c], alpha=0.55, edgecolors="none",
                   label=f"cluster {c + 1} (n={m.sum()}): vz {cen['preimpact_vz']:.2f} m/s, tilt {cen['tilt_rms_deg']:.1f}°, "
                         f"lateral {cen['lateral_speed']:.2f} m/s")
    ax.set_xlabel(f"PC1 ({ex[0]:.0f}% of variance)"); ax.set_ylabel(f"PC2 ({ex[1]:.0f}%)")
    alt = ", ".join(f"k={k}: {v:.2f}" for k, v in K["silhouette"].items() if k != K["k"])
    ax.set_title(f"k-means on 7 flight features, PCA view\nk = {K['k']} by mean silhouette {K['best_silhouette']:.2f} ({alt})",
                 fontsize=10)
    ax.set_ylim(S[:, 1].min() - 2.8, S[:, 1].max() + 0.5)   # room for the legend below the data
    ax.legend(loc="lower left", fontsize=8, markerscale=2.5, frameon=True, framealpha=0.9, edgecolor=GRID)
    # standardized centroids heatmap-like bars
    Zc = np.array([[K["Z"][K["labels"] == c, j].mean() for j in range(len(flight.FEATURES))] for c in range(K["k"])])
    y = np.arange(len(flight.FEATURES)); h = 0.8 / K["k"]
    for c in range(K["k"]):
        ax2.barh(y + (c - (K["k"] - 1) / 2) * h, Zc[c], height=h * 0.9, color=cols[c], label=f"cluster {c + 1}")
    ax2.set_yticks(y, [s.replace("_", " ") for s in flight.FEATURES]); ax2.invert_yaxis()
    ax2.axvline(0, color=INK2, lw=0.8); ax2.set_xlabel("centroid (z-score)"); ax2.set_title("What separates the clusters")
    ax2.grid(axis="y", visible=False); ax2.legend(loc="lower right", fontsize=8)
    _footer(fig)
    fig.savefig(figs / "flight_clusters.png"); plt.close(fig)
    return summ


# ---------------------------------------------------------------- surrogate / sobol data
def default_data(out: Path, rebuild: bool = False, cache_root: str = "", max_designs: int = 1500):
    path = out / "surrogate_data.csv"
    T = flight_table(out, rebuild, cache_root)
    D = flight.design_means(T, "preimpact_vz")
    rng = np.random.default_rng(0)
    idx = np.arange(len(D["q"]))
    if len(idx) > max_designs:
        idx = np.sort(rng.permutation(len(idx))[:max_designs])
    rows = [{k: (int(D[k][i]) if k == "n_drops" else float(D[k][i])) for k in D} for i in idx]
    _write(path, rows)
    return path


def load_xy(data: Path, x_cols, y_col, group_col=None):
    T = flight.read_csv(data)
    X = np.column_stack([T[c] for c in x_cols]); y = T[y_col]
    ok = np.all(np.isfinite(X), 1) & np.isfinite(y)
    g = T[group_col][ok] if group_col else np.arange(ok.sum())
    return X[ok], y[ok], g


def run_surrogate(out: Path, data: Path, x_cols, y_col, group_col=None, n_folds=10):
    X, y, g = load_xy(data, x_cols, y_col, group_col)
    t0 = time.time()
    rows, pred = surrogates.leave_geometry_out_cv(X, y, g, surrogates.MODEL_NAMES, n_folds)
    _write(out / "surrogate_cv.csv", rows)
    for r in rows:
        print(f"  {r['model']:10s} rmse {r['rmse']:.5f}  mae {r['mae']:.5f}  rank_corr {r['rank_corr']:.3f}")
    print(f"surrogate CV ({len(y)} rows, {len(np.unique(g))} geometries, {n_folds} folds) in {time.time() - t0:.0f} s")
    plt = _plt()
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.6), constrained_layout=True, sharex=True, sharey=True)
    lo, hi = np.percentile(y, [0.5, 99.5])
    for ax, r, j in zip(axes, rows, range(4)):
        ax.scatter(y, pred[:, j], s=6, color=C_BLUE, alpha=0.4, edgecolors="none")
        ax.plot([lo, hi], [lo, hi], color=INK2, lw=0.8)
        ax.set_title(f"{r['model']}: RMSE {r['rmse']:.4f}, ρ {r['rank_corr']:.2f}", fontsize=9)
        ax.set_xlabel(f"simulated {y_col}"); ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
    axes[0].set_ylabel("predicted (held-out geometry)")
    fig.suptitle("Surrogate accuracy on unseen designs (leave-geometry-out CV)", fontsize=11)
    _footer(fig)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "figures" / "surrogate_cv.png"); plt.close(fig)
    return rows


def run_sobol(out: Path, data: Path, x_cols, y_col, N=4000):
    X, y, _ = load_xy(data, x_cols, y_col)
    M = surrogates.fit_models(X, y, ["gp"])["gp"]
    surrogates.save_model(M, out / "models" / f"gp_{y_col}.pkl")
    if list(x_cols) == ["q", "slit_len", "slit_r"]:
        lb, ub = param3_bounds()
    else:
        lb, ub = X.min(0), X.max(0)
    S = sensitivity.sobol_indices(M.predict, lb, ub, N, seed=0, n_boot=200)
    rows = [{"var": v, "first": float(S["first"][i]), "total": float(S["total"][i]),
             "first_lo": float(S["first_ci"][0, i]), "first_hi": float(S["first_ci"][1, i]),
             "total_lo": float(S["total_ci"][0, i]), "total_hi": float(S["total_ci"][1, i])} for i, v in enumerate(x_cols)]
    _write(out / "sobol.csv", rows)
    for r in rows:
        print(f"  {r['var']:10s} S1 {r['first']:.3f}  ST {r['total']:.3f}")
    plt = _plt()
    figs = out / "figures"; figs.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.0, 3.8), constrained_layout=True)
    x = np.arange(len(x_cols)); w = 0.36
    for off, key, col, lab in ((-w / 2, "first", C_BLUE, "first-order S1"), (w / 2, "total", C_ORANGE, "total ST")):
        v = np.array([r[key] for r in rows])
        e = np.array([[r[key] - r[key + "_lo"] for r in rows], [r[key + "_hi"] - r[key] for r in rows]])
        ax.bar(x + off, v, w * 0.92, color=col, label=lab, yerr=np.clip(e, 0, None), ecolor=INK2, capsize=3)
        for xi, vi in zip(x + off, v):
            ax.text(xi, vi + 0.03, f"{vi:.2f}", ha="center", fontsize=8, color=INK)
    ax.set_xticks(x, [c.replace("_", " ") for c in x_cols]); ax.set_ylim(0, 1.0)
    ax.set_ylabel("Sobol index"); ax.grid(axis="x", visible=False); ax.legend(loc="upper left")
    ax.set_title(f"Sensitivity of {y_col} (GP surrogate, N = {N}, 95% bootstrap CI)", fontsize=10)
    _footer(fig)
    fig.savefig(figs / "sobol.png"); plt.close(fig)
    sensitivity.interaction_plot(M.predict, lb, ub, [c.replace("_", " ") for c in x_cols], figs / "interactions.png",
                                 L2, label=y_col)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--what", default="all", choices=["rep", "surrogate", "sobol", "flight", "all"])
    ap.add_argument("--out", default=str(REPO_ROOT / "results" / "studies_v2"))
    ap.add_argument("--data", default="", help="CSV with feature + target columns (default: built from cache)")
    ap.add_argument("--x-cols", default="q,slit_len,slit_r")
    ap.add_argument("--y-col", default="preimpact_vz")
    ap.add_argument("--group-col", default="", help="geometry id column (default: each row its own geometry)")
    ap.add_argument("--folds", type=int, default=10)
    ap.add_argument("--sobol-n", type=int, default=4000)
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--cache-root", default="")
    ap.add_argument("--rebuild-flight", action="store_true", help="re-read the cache even if flight_features.csv exists")
    a = ap.parse_args(argv)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    what = ["rep", "flight", "surrogate", "sobol"] if a.what == "all" else [a.what]
    if "rep" in what:
        run_rep(out, a.epochs)
    if "flight" in what:
        run_flight(out, a.rebuild_flight, a.cache_root)
    if "surrogate" in what or "sobol" in what:
        data = Path(a.data) if a.data else default_data(out, a.rebuild_flight and "flight" not in what, a.cache_root)
        xc = a.x_cols.split(",")
        if "surrogate" in what:
            run_surrogate(out, data, xc, a.y_col, a.group_col or None, a.folds)
        if "sobol" in what:
            run_sobol(out, data, xc, a.y_col, a.sobol_n)


if __name__ == "__main__":
    main()
