"""Shape representations: dataset of area-normalised radial outlines, PCA / autoencoder / VAE studies.

Port of matlab/+chute/+rep/{shapeDataset, normalizeArea, isValidShape, pcaStudy, aeStudy, vaeStudy}.m.
Outlines are r(theta)/R_eq sampled at n_theta equally spaced angles; after area normalisation the polar
polygon has area pi, i.e. A0 (250 cm^2) when scaled by R_eq = sqrt(A0/pi).

Random streams differ from MATLAB (numpy PCG64 vs Mersenne twister, PyTorch init vs Glorot), so the
numbers agree statistically, not bit for bit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.spatial.distance import pdist

N_THETA = 64


# ------------------------------------------------------------------ geometry helpers
def theta(n: int = N_THETA) -> np.ndarray:
    return np.arange(n) * 2 * np.pi / n


def polar_area(R: np.ndarray) -> np.ndarray:
    """Area of the polar polygon(s) through radial samples (rows), units of R_eq^2."""
    R = np.atleast_2d(np.asarray(R, float))
    n = R.shape[1]
    return 0.5 * np.sin(2 * np.pi / n) * np.sum(R * np.roll(R, -1, axis=1), axis=1)


def normalize_area(R: np.ndarray) -> np.ndarray:
    """Scale radial samples so the polar polygon has area pi (= A0 in R_eq units)."""
    R = np.asarray(R, float)
    one = R.ndim == 1
    R2 = np.atleast_2d(R)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = R2 * np.sqrt(np.pi / polar_area(R2))[:, None]
    return out[0] if one else out


def is_valid_shape(R: np.ndarray) -> np.ndarray:
    """Geometric validity / fabrication checks (same thresholds as isValidShape.m and
    chutesim.geometry.check_feasible): 0.35 < r < 2.2, neighbour jump < 0.25, finite."""
    R = np.atleast_2d(np.asarray(R, float))
    dr = np.abs(R - np.roll(R, -1, axis=1))
    with np.errstate(invalid="ignore"):
        return (np.all(R > 0.35, 1) & np.all(R < 2.2, 1) & np.all(dr < 0.25, 1) & np.all(np.isfinite(R), 1))


def shape_dataset(n: int, seed: int = 1, n_theta: int = N_THETA):
    """Rich canopy outlines: superellipses (35%), Fourier-perturbed circles (40%, half 4-fold symmetric),
    rounded polygons (25%), all area-normalised. Returns (R (n, n_theta), info dict)."""
    rng = np.random.default_rng(seed)
    th = theta(n_theta)
    R = np.zeros((n, n_theta))
    fam = []
    for i in range(n):
        u = rng.random()
        if u < 0.35:
            q = 2 + 6 * rng.random()
            r = (np.abs(np.cos(th)) ** q + np.abs(np.sin(th)) ** q) ** (-1 / q)
            fam.append("superellipse")
        elif u < 0.75:
            r = np.ones(n_theta)
            sym = rng.random() < 0.5
            for k in range(2, 9):
                if sym and k % 4 != 0:
                    continue
                r = r + (0.15 / k) * rng.standard_normal() * np.cos(k * th + 2 * np.pi * rng.random())
            fam.append("fourier")
        else:
            m = int(rng.integers(3, 9))
            rho = 0.15 + 0.5 * rng.random()
            phi = np.mod(th + np.pi / m, 2 * np.pi / m) - np.pi / m
            r = np.cos(np.pi / m) / np.cos(phi)
            r = (1 - rho) * r + rho
            fam.append("rounded_polygon")
        R[i] = normalize_area(r)
    return R, {"family": np.array(fam), "valid": is_valid_shape(R), "theta": th}


# ------------------------------------------------------------------ PCA
@dataclass
class PCAModel:
    mu: np.ndarray
    coeff: np.ndarray          # (d, d) principal directions as columns
    explained: np.ndarray      # percent variance per component

    def encode(self, R, k):
        return (np.atleast_2d(R) - self.mu) @ self.coeff[:, :k]

    def decode(self, Z, normalize: bool = True):
        Z = np.atleast_2d(np.asarray(Z, float))
        Rh = Z @ self.coeff[:, :Z.shape[1]].T + self.mu
        return normalize_area(Rh) if normalize else Rh

    def save(self, path):
        np.savez(path, mu=self.mu, coeff=self.coeff, explained=self.explained)

    @classmethod
    def load(cls, path):
        d = np.load(path)
        return cls(d["mu"], d["coeff"], d["explained"])


def fit_pca(R) -> PCAModel:
    mu = R.mean(0)
    _, s, Vt = np.linalg.svd(R - mu, full_matrices=False)
    # sign convention as MATLAB pca: largest-magnitude element of each coefficient vector positive
    V = Vt.T
    sgn = np.sign(V[np.argmax(np.abs(V), axis=0), np.arange(V.shape[1])])
    V = V * np.where(sgn == 0, 1, sgn)
    return PCAModel(mu, V, 100 * s**2 / np.sum(s**2))


def pca_study(R, ks=(2, 3, 4, 6, 8, 12)):
    """Variance retained, reconstruction RMSE and validity of (area-normalised) reconstructions vs k."""
    P = fit_pca(R)
    rows = []
    for k in ks:
        Rh = P.decode(P.encode(R, k), normalize=False)
        rows.append({"k": int(k), "var_retained_pct": float(P.explained[:k].sum()),
                     "recon_rmse": float(np.sqrt(np.mean((Rh - R) ** 2))),
                     "valid_rate": float(np.mean(is_valid_shape(normalize_area(Rh))))})
    return {"model": P, "table": rows}


# ------------------------------------------------------------------ autoencoder / VAE (PyTorch)
def _torch():
    import torch
    torch.set_num_threads(min(8, torch.get_num_threads()))
    return torch


def _mlp(sizes, torch):
    nn = torch.nn
    layers = []
    for i in range(len(sizes) - 1):
        layers.append(nn.Linear(sizes[i], sizes[i + 1]))
        if i < len(sizes) - 2:
            layers.append(nn.Tanh())
    return nn.Sequential(*layers)


@dataclass
class AEModel:
    """MLP autoencoder d-48-tanh-k-48-tanh-d on standardised outlines (z-scored per angle)."""
    k: int
    mu: np.ndarray
    sd: np.ndarray
    enc: object = field(repr=False)
    dec: object = field(repr=False)
    hidden: int = 48

    def encode(self, R):
        torch = _torch()
        X = torch.as_tensor((np.atleast_2d(R) - self.mu) / self.sd, dtype=torch.float32)
        with torch.no_grad():
            return self.enc(X).double().numpy()

    def decode(self, Z, normalize: bool = True):
        torch = _torch()
        with torch.no_grad():
            Y = self.dec(torch.as_tensor(np.atleast_2d(Z), dtype=torch.float32)).double().numpy()
        Rh = Y * self.sd + self.mu
        return normalize_area(Rh) if normalize else Rh

    def save(self, path):
        torch = _torch()
        path = Path(path)
        torch.save({"enc": self.enc.state_dict(), "dec": self.dec.state_dict()}, path.with_suffix(".pt"))
        np.savez(path.with_suffix(".npz"), mu=self.mu, sd=self.sd, k=self.k, hidden=self.hidden, kind=type(self).__name__)

    @classmethod
    def load(cls, path):
        torch = _torch()
        path = Path(path)
        m = np.load(path.with_suffix(".npz"))
        k, h, d = int(m["k"]), int(m["hidden"]), len(m["mu"])
        enc, dec = _mlp([d, h, k], torch), _mlp([k, h, d], torch)
        st = torch.load(path.with_suffix(".pt"), weights_only=True)
        enc.load_state_dict(st["enc"]); dec.load_state_dict(st["dec"])
        enc.eval(); dec.eval()
        return cls(k, m["mu"], m["sd"], enc, dec, h)


def train_ae(Rtr, k, epochs=150, seed=0, hidden=48, lr=3e-3, batch=128, weight_decay=1e-4) -> AEModel:
    """Adam, mini-batch 128, lr 3e-3, L2 1e-4 (trainingOptions defaults used by aeStudy.m)."""
    torch = _torch()
    torch.manual_seed(seed)
    mu = Rtr.mean(0); sd = Rtr.std(0, ddof=1) + 1e-6
    X = torch.as_tensor((Rtr - mu) / sd, dtype=torch.float32)
    d = X.shape[1]
    enc, dec = _mlp([d, hidden, k], torch), _mlp([k, hidden, d], torch)
    params = list(enc.parameters()) + list(dec.parameters())
    opt = torch.optim.Adam(params, lr=lr, weight_decay=weight_decay)
    g = torch.Generator().manual_seed(seed)
    n = X.shape[0]
    for _ in range(epochs):
        p = torch.randperm(n, generator=g)
        for s in range(0, n, batch):
            xb = X[p[s:s + batch]]
            loss = torch.mean((dec(enc(xb)) - xb) ** 2)
            opt.zero_grad(); loss.backward(); opt.step()
    enc.eval(); dec.eval()
    return AEModel(k, mu, sd, enc, dec, hidden)


def split_train_test(n, seed=0, test_frac=0.2):
    rng = np.random.default_rng(seed)
    te = np.zeros(n, bool)
    te[rng.permutation(n)[:round(test_frac * n)]] = True
    return te


def _train_ae_job(args):
    Rtr, k, epochs, seed = args
    torch = _torch()
    torch.set_num_threads(1)
    m = train_ae(Rtr, k, epochs=epochs, seed=seed)
    return k, m.mu, m.sd, m.enc.state_dict(), m.dec.state_dict()


def ae_study(R, ks=(2, 3, 4, 6, 8), epochs=150, seed=0, n_jobs: int | None = None):
    """Held-out (20%) reconstruction RMSE and validity of decoded test shapes for each latent size k.
    Also reports the mean-shape baseline RMSE (reconstruct every test shape by the training mean).
    The k values train in parallel processes (n_jobs; 1 = in-process)."""
    te = split_train_test(len(R), seed)
    Rtr, Rte = R[~te], R[te]
    base = float(np.sqrt(np.mean((Rte - Rtr.mean(0)) ** 2)))
    ks = [int(k) for k in ks]
    n_jobs = min(len(ks), 8) if n_jobs is None else n_jobs
    models = {}
    if n_jobs <= 1:
        for k in ks:
            models[k] = train_ae(Rtr, k, epochs=epochs, seed=seed)
    else:
        import multiprocessing as mp
        torch = _torch()
        with mp.get_context("spawn").Pool(n_jobs) as pool:
            for k, mu, sd, se, sdict in pool.map(_train_ae_job, [(Rtr, k, epochs, seed) for k in ks]):
                d = Rtr.shape[1]
                enc, dec = _mlp([d, 48, k], torch), _mlp([k, 48, d], torch)
                enc.load_state_dict(se); dec.load_state_dict(sdict); enc.eval(); dec.eval()
                models[k] = AEModel(k, mu, sd, enc, dec, 48)
    rows = []
    for k in ks:
        m = models[k]
        Rh = m.decode(m.encode(Rte), normalize=False)
        rows.append({"k": k, "test_recon_rmse": float(np.sqrt(np.mean((Rh - Rte) ** 2))),
                     "valid_rate": float(np.mean(is_valid_shape(normalize_area(Rh)))),
                     "mean_shape_rmse": base})
    return {"models": models, "table": rows, "test_mask": te}


@dataclass
class VAEModel:
    """VAE: encoder d-64-tanh-2k (mean, log-variance), decoder k-64-tanh-d, prior N(0, I)."""
    k: int
    mu: np.ndarray
    sd: np.ndarray
    enc: object = field(repr=False)
    dec: object = field(repr=False)
    hidden: int = 64

    def encode(self, R):
        torch = _torch()
        with torch.no_grad():
            h = self.enc(torch.as_tensor((np.atleast_2d(R) - self.mu) / self.sd, dtype=torch.float32))
        return h[:, :self.k].double().numpy()

    def decode(self, Z, normalize: bool = True):
        torch = _torch()
        with torch.no_grad():
            Y = self.dec(torch.as_tensor(np.atleast_2d(Z), dtype=torch.float32)).double().numpy()
        Rh = Y * self.sd + self.mu
        return normalize_area(Rh) if normalize else Rh

    def sample(self, n, seed=0):
        Z = np.random.default_rng(seed).standard_normal((n, self.k))
        return self.decode(Z)

    save = AEModel.save

    @classmethod
    def load(cls, path):
        torch = _torch()
        path = Path(path)
        m = np.load(path.with_suffix(".npz"))
        k, h, d = int(m["k"]), int(m["hidden"]), len(m["mu"])
        enc, dec = _mlp([d, h, 2 * k], torch), _mlp([k, h, d], torch)
        st = torch.load(path.with_suffix(".pt"), weights_only=True)
        enc.load_state_dict(st["enc"]); dec.load_state_dict(st["dec"])
        enc.eval(); dec.eval()
        return cls(k, m["mu"], m["sd"], enc, dec, h)


def train_vae(R, k=4, epochs=150, beta=0.05, seed=0, hidden=64, lr=2e-3, batch=128) -> VAEModel:
    torch = _torch()
    torch.manual_seed(seed)
    mu = R.mean(0); sd = R.std(0, ddof=1) + 1e-6
    X = torch.as_tensor((R - mu) / sd, dtype=torch.float32)
    d = X.shape[1]
    enc, dec = _mlp([d, hidden, 2 * k], torch), _mlp([k, hidden, d], torch)
    opt = torch.optim.Adam(list(enc.parameters()) + list(dec.parameters()), lr=lr)
    g = torch.Generator().manual_seed(seed)
    n = X.shape[0]
    for _ in range(epochs):
        p = torch.randperm(n, generator=g)
        for s in range(0, n, batch):
            xb = X[p[s:s + batch]]
            h = enc(xb)
            m, lv = h[:, :k], h[:, k:]
            z = m + torch.exp(0.5 * lv) * torch.randn(m.shape, generator=g)
            rec = torch.mean(torch.sum((dec(z) - xb) ** 2, 1))
            kl = torch.mean(-0.5 * torch.sum(1 + lv - m**2 - torch.exp(lv), 1))
            loss = rec + beta * kl
            opt.zero_grad(); loss.backward(); opt.step()
    enc.eval(); dec.eval()
    return VAEModel(k, mu, sd, enc, dec, hidden)


def vae_study(R, k=4, epochs=150, beta=0.05, n_generate=500, seed=0):
    """Generated-shape validity rate and diversity (mean pairwise distance of valid generated shapes)
    vs data diversity (mean pairwise distance of 500 random training shapes)."""
    V = train_vae(R, k, epochs, beta, seed)
    G = V.sample(n_generate, seed)
    ok = is_valid_shape(G)
    rng = np.random.default_rng(seed)
    sub = R[rng.permutation(len(R))[:min(len(R), 500)]]
    return {"model": V, "generated": G, "valid_rate": float(ok.mean()),
            "diversity": float(pdist(G[ok]).mean()) if ok.sum() > 1 else float("nan"),
            "data_diversity": float(pdist(sub).mean())}


# ------------------------------------------------------------------ persistence of a full study
def save_models(out_dir, pca: PCAModel | None = None, aes: dict | None = None, vae: VAEModel | None = None):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    if pca is not None:
        pca.save(out / "pca.npz")
    for k, m in (aes or {}).items():
        m.save(out / f"ae_k{k}")
    if vae is not None:
        vae.save(out / f"vae_k{vae.k}")
    (out / "models.json").write_text(json.dumps({"pca": pca is not None, "ae_k": sorted((aes or {}).keys()),
                                                 "vae_k": vae.k if vae is not None else None}))


def load_models(out_dir):
    out = Path(out_dir)
    meta = json.loads((out / "models.json").read_text())
    pca = PCAModel.load(out / "pca.npz") if meta["pca"] else None
    aes = {k: AEModel.load(out / f"ae_k{k}") for k in meta["ae_k"]}
    vae = VAEModel.load(out / f"vae_k{meta['vae_k']}") if meta["vae_k"] is not None else None
    return {"pca": pca, "ae": aes, "vae": vae}
