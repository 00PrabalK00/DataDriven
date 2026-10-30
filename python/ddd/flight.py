"""Flight-feature data from the evaluation cache, PCA summary and k-means behaviour groups.

Port of matlab/+chute/+analysis/flightClusters.m and the data steps of matlab/scripts/m10_studies.m.
The per-drop table comes from chutesim.bridge.flight_features_csv (what MATLAB called through
chute.bridge.call('flight_features_csv', file, '', 'fused')).
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

FEATURES = ("preimpact_vz", "lateral_speed", "landing_offset", "tilt_rms_deg", "tilt_max_deg", "swing_rate_rms",
            "peak_specific_force_g")
DESIGN_COLS = ("q", "slit_len", "slit_r")


def build_flight_features(path, cache_root: str = "", mode: str = "fused") -> int:
    """Write the per-drop flight-feature CSV from the evaluation cache (default data/cache)."""
    import json

    from chutesim.bridge import flight_features_csv
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return json.loads(flight_features_csv(str(path), cache_root, mode))["rows"]


def read_csv(path) -> dict[str, np.ndarray]:
    """CSV -> {column: array}; numeric columns as float (empty -> NaN), others as str."""
    with open(path, newline="") as f:
        r = csv.reader(f)
        head = next(r)
        cols = list(zip(*r)) or [()] * len(head)
    out = {}
    for h, c in zip(head, cols):
        try:
            out[h] = np.array([float(v) if v != "" else np.nan for v in c])
        except ValueError:
            out[h] = np.array(c)
    return out


def write_csv(path, rows: list[dict]):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def complete_rows(T: dict, feats=FEATURES) -> dict:
    ok = np.all([np.isfinite(T[k]) for k in feats], axis=0)
    return {k: v[ok] for k, v in T.items()}


def design_means(T: dict, target: str = "preimpact_vz") -> dict:
    """Scenario-averaged target per unique design (q, slit_len, slit_r), as m10_studies.m."""
    X = np.column_stack([T[c] for c in DESIGN_COLS])
    u, inv, cnt = np.unique(X, axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    y = np.bincount(inv, weights=T[target]) / cnt
    return {"q": u[:, 0], "slit_len": u[:, 1], "slit_r": u[:, 2], target: y, "n_drops": cnt}


def flight_clusters(F, names=FEATURES, k_range=range(2, 7), seed: int = 0, n_init: int = 20,
                    silhouette_metric: str = "sqeuclidean"):
    """z-score F, PCA (variance explained, components for 90%), k-means for each k (20 restarts),
    k chosen by mean silhouette; centroids reported in original units.

    silhouette_metric 'sqeuclidean' reproduces MATLAB's silhouette() default (squared Euclidean);
    the Euclidean silhouette (scikit-learn default, lower values) is reported alongside."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    F = np.asarray(F, float)
    Z = (F - F.mean(0)) / F.std(0, ddof=1)
    _, s, Vt = np.linalg.svd(Z - Z.mean(0), full_matrices=False)
    explained = 100 * s**2 / np.sum(s**2)
    score = (Z - Z.mean(0)) @ Vt.T
    sil, sil_euc, labels = {}, {}, {}
    for k in k_range:
        if k >= len(Z):
            continue
        km = KMeans(k, n_init=n_init, max_iter=500, random_state=seed).fit(Z)
        labels[k] = km.labels_
        sil[k] = float(silhouette_score(Z, km.labels_, metric=silhouette_metric))
        sil_euc[k] = float(silhouette_score(Z, km.labels_, metric="euclidean"))
    kb = max(sil, key=sil.get)
    idx = labels[kb]
    # order clusters by size (largest first) for a stable presentation
    order = np.argsort(-np.bincount(idx))
    remap = np.empty_like(order); remap[order] = np.arange(len(order))
    idx = remap[idx]
    cent = [{"cluster": c + 1, "n": int(np.sum(idx == c)), **{n: float(F[idx == c, j].mean()) for j, n in enumerate(names)}}
            for c in range(kb)]
    return {"k": kb, "silhouette": sil, "silhouette_euclidean": sil_euc,
            "best_silhouette": sil[kb], "labels": idx, "centroids": cent,
            "pca": {"explained": explained, "coeff": Vt.T, "score": score,
                    "n_for_90": int(np.searchsorted(np.cumsum(explained), 90) + 1)},
            "meaningful": sil[kb] > 0.5, "Z": Z}
