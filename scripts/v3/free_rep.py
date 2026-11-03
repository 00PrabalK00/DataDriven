"""Representation study on free-form canopies (course wk 3): PCA, autoencoder, VAE on rasterised plastic masks.

Dataset: Latin-hypercube field weights (D6), feasible designs only, each rasterised to a 48 x 48 mask.
Reports reconstruction IoU on held-out shapes vs latent size, and VAE samples (validity, novelty).
  python/.venv/bin/python scripts/v3/free_rep.py --n 2400 --workers 16
Output: results/freeform/rep/ (masks.npz, rep_summary.json, rep_overview.png).
"""
import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
OUT = ROOT / "results" / "freeform" / "rep"
N_PX = 48
SPAN = 0.135  # half-width of the raster [m]; the 30 cm span rule allows at most 0.15, typical shapes fit


def raster(g):
    from matplotlib.path import Path as MplPath
    s = np.linspace(-SPAN, SPAN, N_PX)
    X, Y = np.meshgrid(s, s)
    P = np.column_stack([X.ravel(), Y.ravel()])
    m = MplPath(g.outline).contains_points(P)
    for h in g.holes:
        m &= ~MplPath(h).contains_points(P)
    return m.reshape(N_PX, N_PX)


def _one(w):
    from chutesim.config import load_config
    from chutesim.freeform import build_free_geometry, free_design
    g = build_free_geometry(free_design(w, "D6"), load_config(None))
    return g.feasible, raster(g)


def iou(a, b):
    a, b = a > 0.5, b > 0.5
    return (a & b).sum((1, 2)) / np.maximum((a | b).sum((1, 2)), 1)


def net(sizes, torch):
    layers = []
    for i in range(len(sizes) - 1):
        layers.append(torch.nn.Linear(sizes[i], sizes[i + 1]))
        if i < len(sizes) - 2:
            layers.append(torch.nn.ReLU())
    return torch.nn.Sequential(*layers)


def train(X, Xte, k, vae, epochs, torch, beta=2e-3, hidden=256):
    torch.manual_seed(0)
    d = X.shape[1]
    enc, dec = net([d, hidden, (2 if vae else 1) * k], torch), net([k, hidden, d], torch)
    opt = torch.optim.Adam(list(enc.parameters()) + list(dec.parameters()), lr=1e-3)
    T = torch.as_tensor(X, dtype=torch.float32)
    bce = torch.nn.functional.binary_cross_entropy_with_logits
    for _ in range(epochs):
        for idx in torch.randperm(len(T)).split(64):
            x = T[idx]
            h = enc(x)
            if vae:
                mu, lv = h[:, :k], h[:, k:]
                z = mu + torch.exp(0.5 * lv) * torch.randn_like(mu)
                loss = bce(dec(z), x) + beta * (-0.5 * (1 + lv - mu**2 - lv.exp()).sum(1).mean())
            else:
                loss = bce(dec(h), x)
            opt.zero_grad()
            loss.backward()
            opt.step()
    with torch.no_grad():
        h = enc(torch.as_tensor(Xte, dtype=torch.float32))
        rec = torch.sigmoid(dec(h[:, :k])).numpy()
        samp = torch.sigmoid(dec(torch.randn(500, k))).numpy() if vae else None
    return rec, samp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2400)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--epochs", type=int, default=60)
    a = ap.parse_args()
    import torch
    from scipy.ndimage import label
    from scipy.stats import qmc
    from chutesim.freeform import n_weights
    torch.set_num_threads(a.workers)
    OUT.mkdir(parents=True, exist_ok=True)
    k = n_weights("D6")
    W = qmc.scale(qmc.LatinHypercube(d=k, seed=5).random(a.n), -1.6 * np.ones(k), 1.6 * np.ones(k))
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(_one, W, chunksize=8))
    ok = np.array([r[0] for r in res])
    M = np.array([r[1] for r, o in zip(res, ok) if o], dtype=np.float32)
    W = W[ok]
    print(f"{ok.sum()}/{len(ok)} feasible", flush=True)
    np.savez_compressed(OUT / "masks.npz", masks=M.astype(bool), weights=W)
    rng = np.random.default_rng(0)
    p = rng.permutation(len(M))
    nt = len(M) // 5
    te, tr = M[p[:nt]], M[p[nt:]]
    Xtr, Xte = tr.reshape(len(tr), -1), te.reshape(len(te), -1)
    mu = Xtr.mean(0)
    _, S, Vt = np.linalg.svd(Xtr - mu, full_matrices=False)
    var = S**2 / (S**2).sum()
    out = {"n_shapes": len(M), "feasible_frac": float(ok.mean()), "pca_var_cum": np.cumsum(var)[:30].tolist(), "iou": {}}
    ks = (2, 4, 6, 9, 16)
    for z in ks:
        rec = ((Xte - mu) @ Vt[:z].T @ Vt[:z] + mu).reshape(te.shape)
        out["iou"][f"pca_{z}"] = float(iou(rec, te).mean())
    gal = {}
    for z in ks:
        for name, vae in (("ae", False), ("vae", True)):
            r, samp = train(Xtr, Xte, z, vae, a.epochs, torch)
            out["iou"][f"{name}_{z}"] = float(iou(r.reshape(te.shape), te).mean())
            if vae:
                s = samp.reshape(-1, N_PX, N_PX) > 0.5
                ncomp = np.array([label(x)[1] for x in s])
                nov = np.array([(1 - iou(np.repeat(x[None], 300, 0).astype(float), tr[:300])).min() for x in s[:100]])
                out[f"vae_{z}_one_piece_frac"] = float((ncomp == 1).mean())
                out[f"vae_{z}_novelty"] = float(nov.mean())
                gal[z] = s
            print(z, name, round(out["iou"][f"{name}_{z}"], 4), flush=True)
            (OUT / "rep_summary.json").write_text(json.dumps(out, indent=1))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 3, figsize=(16, 4.8), gridspec_kw={"width_ratios": [1, 1, 1.5]})
    axs[0].plot(range(1, 31), 100 * np.cumsum(var)[:30], "o-", ms=3)
    axs[0].set_xlabel("principal components")
    axs[0].set_ylabel("variance retained [%]")
    axs[0].set_title("PCA on canopy masks")
    axs[0].grid(alpha=.3)
    for name, c in (("pca", "#4c72b0"), ("ae", "#dd8452"), ("vae", "#55a868")):
        axs[1].plot(ks, [out["iou"][f"{name}_{z}"] for z in ks], "o-", c=c, label=name.upper())
    axs[1].set_xlabel("latent dimension")
    axs[1].set_ylabel("held-out IoU")
    axs[1].set_title("Reconstruction of unseen shapes")
    axs[1].legend()
    axs[1].grid(alpha=.3)
    axs[2].axis("off")
    S_ = gal[9][:24]
    grid = np.vstack([np.hstack(S_[i:i + 8]) for i in range(0, 24, 8)])
    axs[2].imshow(grid, cmap="Blues", interpolation="nearest")
    axs[2].set_title("VAE-generated canopies (9-D latent)")
    fig.suptitle(f"Dimensionality reduction on {len(M)} feasible free-form canopies", weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "rep_overview.png", dpi=120)
    print("done")


if __name__ == "__main__":
    main()
