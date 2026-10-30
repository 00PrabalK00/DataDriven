"""Form-finding: 2D canopy cut pattern -> inflated 3D canopy shape (dynamic relaxation).

Model (quasi-static, one-way coupled, assumption L2):
- membrane: triangulated flat sheet with the real outline; slits are real cuts (nodes duplicated along
  each slit, tips shared) so the two sides can separate under load; cut-outs (vent / holes, chutesim.cutouts)
  are removed from the sheet (free inner boundaries);
- in-plane: tension-only edge springs, k_e = E*t * (adjacent triangle area) / L_e^2 (wrinkling sheet);
- bending: quadratic isometric bending model (Bergou et al. 2006), B = E t^3 / 12 (times bend_scale);
  it regularises wrinkles at mesh scale;
- load: uniform follower pressure p (default 0.5*rho*U^2 with U=7 m/s) along the surface normal (+z side);
- suspension lines (count/azimuths from the payload anchors in cfg): tension-only springs of rest length
  canopy.line_length_m from the canopy attach points to the payload anchors (fixed; payload hangs below).
  Freestream for CFD runs along +z into the concave (mouth) side.
Integration: explicit dynamic relaxation with fictitious masses and kinetic damping; stiffness continuation.
Frame: payload frame (anchors as in cfg), canopy axis +z above the payload.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
from matplotlib.path import Path as MplPath
from scipy.spatial import Delaunay

from chutesim.config import load_config
from chutesim.geometry import Design, build_geometry


# ----------------------------------------------------------------------------------------------- mesh
@dataclass
class FlatMesh:
    """Flat cut mesh: nodes (N,2), tris (M,3) CCW, attach node ids, slit side node chains."""
    xy: np.ndarray
    tris: np.ndarray
    attach: np.ndarray
    slit_loops: list = field(default_factory=list)  # per slit: (side_a ids tip->tip, side_b ids tip->tip)
    hole_loops: list = field(default_factory=list)  # per cut-out: boundary node ids in order


def _resample_closed(poly: np.ndarray, h: float, keep: np.ndarray | None = None) -> np.ndarray:
    """Resample a closed polygon at spacing ~h, forcing the points `keep` (snapped) to be vertices."""
    seg = np.linalg.norm(np.roll(poly, -1, 0) - poly, axis=1)
    s = np.r_[0.0, np.cumsum(seg)]
    P = s[-1]
    n = max(int(round(P / h)), 12)
    t = np.linspace(0, P, n, endpoint=False)
    if keep is not None and len(keep):
        tk = []
        for p in keep:
            i = int(np.argmin(np.linalg.norm(poly - p, axis=1)))
            tk.append(s[i])
        tk = np.array(tk)
        # drop uniform samples too close to forced ones, then merge
        d = np.abs(((t[:, None] - tk[None, :]) + P / 2) % P - P / 2).min(1)
        t = np.sort(np.r_[t[d > 0.45 * P / n], tk])
    x = np.interp(t, s, np.r_[poly[:, 0], poly[0, 0]])
    y = np.interp(t, s, np.r_[poly[:, 1], poly[0, 1]])
    return np.column_stack([x, y])


def _seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    t = np.clip(((p - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def _crosses(p0, p1, a, b) -> np.ndarray:
    """Proper intersection of segments p0-p1 (arrays) with segment a-b."""
    def orient(u, v, w):
        return (v[..., 0] - u[..., 0]) * (w[..., 1] - u[..., 1]) - (v[..., 1] - u[..., 1]) * (w[..., 0] - u[..., 0])
    o1 = orient(p0, p1, a)
    o2 = orient(p0, p1, b)
    o3 = orient(a[None], b[None], p0)
    o4 = orient(a[None], b[None], p1)
    eps = 1e-14
    return (o1 * o2 < -eps) & (o3 * o4 < -eps)


def mesh_flat(outline: np.ndarray, slits: np.ndarray, attach_pts: np.ndarray, h: float = 0.004,
              holes: list | tuple = ()) -> FlatMesh:
    """Unstructured flat mesh of the cut pattern: Delaunay on boundary + slit + hole + hex-lattice interior
    points, triangles outside the outline or inside a hole removed, slit cuts made by duplicating
    slit-interior nodes."""
    bnd = _resample_closed(outline, h, keep=attach_pts)
    # hole boundaries: at least 24 points per hole so small holes keep their shape
    hole_pts = [_resample_closed(hp, min(h, float(np.sum(np.linalg.norm(np.roll(hp, -1, 0) - hp, axis=1))) / 24))
                for hp in holes]
    hole_paths = [MplPath(hp) for hp in holes]
    # slit points (finer spacing so the slit edges are Delaunay edges)
    hs = 0.5 * h
    slit_pts = []
    for a, b in slits:
        n = max(int(math.ceil(np.linalg.norm(b - a) / hs)), 2)
        slit_pts.append(a + np.linspace(0, 1, n + 1)[:, None] * (b - a))
    # interior hex lattice
    R = np.abs(outline).max() * 1.05
    ys = np.arange(-R, R, h * math.sqrt(3) / 2)
    pts = []
    for j, y in enumerate(ys):
        xs = np.arange(-R, R, h) + (0.5 * h if j % 2 else 0.0)
        pts.append(np.column_stack([xs, np.full_like(xs, y)]))
    lat = np.vstack(pts)
    path = MplPath(outline)
    lat = lat[path.contains_points(lat)]
    # keep interior points away from boundary and slits
    from scipy.spatial import cKDTree
    db, _ = cKDTree(bnd).query(lat)
    keep = db > 0.6 * h
    for a, b in slits:
        keep &= _seg_dist(lat, a, b) > 0.55 * h
    for hp, hpath in zip(hole_pts, hole_paths):
        keep &= ~hpath.contains_points(lat)
        keep &= cKDTree(hp).query(lat)[0] > 0.6 * h
    lat = lat[keep]
    blocks = [bnd, lat] + slit_pts + hole_pts
    xy = np.vstack(blocks)
    nb = len(bnd)
    off = nb + len(lat)
    slit_ids = []
    for sp_ in slit_pts:
        slit_ids.append(np.arange(off, off + len(sp_)))
        off += len(sp_)
    hole_ids = []
    for hp in hole_pts:
        hole_ids.append(np.arange(off, off + len(hp)))
        off += len(hp)

    tri = Delaunay(xy).simplices
    cen = xy[tri].mean(1)
    tri = tri[path.contains_points(cen, radius=-1e-9) | path.contains_points(cen, radius=1e-9)]
    tri = tri[MplPath(outline).contains_points(xy[tri].mean(1))]
    for hpath in hole_paths:
        tri = tri[~hpath.contains_points(xy[tri].mean(1))]
    # orient CCW
    a, b, c = xy[tri[:, 0]], xy[tri[:, 1]], xy[tri[:, 2]]
    cr = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    tri[cr < 0] = tri[cr < 0][:, [0, 2, 1]]
    tri = tri[np.abs(cr) > 1e-14]
    # drop triangles whose edges cross a slit (should be none when slit edges are conforming)
    for a_, b_ in slits:
        bad = np.zeros(len(tri), bool)
        for e in ((0, 1), (1, 2), (2, 0)):
            bad |= _crosses(xy[tri[:, e[0]]], xy[tri[:, e[1]]], a_, b_)
        tri = tri[~bad]

    # attach nodes = boundary nodes nearest to the requested points
    attach = np.array([int(np.argmin(np.linalg.norm(xy[:nb] - p, axis=1))) for p in attach_pts])

    # cut: duplicate slit-interior nodes for triangles on the "left" side of each slit
    xy = list(xy)
    loops = []
    tri = tri.copy()
    for (a_, b_), ids in zip(slits, slit_ids):
        d = (b_ - a_) / np.linalg.norm(b_ - a_)
        nrm = np.array([-d[1], d[0]])
        inner = ids[1:-1]
        new = np.arange(len(xy), len(xy) + len(inner))
        xy.extend(np.asarray(xy)[inner])
        remap = dict(zip(inner.tolist(), new.tolist()))
        XY = np.asarray(xy)
        cen = XY[tri].mean(1)
        left = (cen - a_) @ nrm > 0
        for k in np.where(left)[0]:
            tri[k] = [remap.get(int(v), int(v)) for v in tri[k]]
        side_a = ids                                    # right side, tip -> tip
        side_b = np.r_[ids[0], new, ids[-1]]            # left side, tip -> tip
        loops.append((side_a, side_b))
    xy = np.asarray(xy)
    # remove unreferenced nodes
    used = np.unique(tri)
    remap = -np.ones(len(xy), int)
    remap[used] = np.arange(len(used))
    loops = [(remap[a], remap[b]) for a, b in loops]
    hloops = [remap[ids] for ids in hole_ids]
    if any((hl < 0).any() for hl in hloops):
        raise ValueError("hole boundary node not used by any triangle (hole too close to another cut or the edge)")
    return FlatMesh(xy[used], remap[tri], remap[attach], loops, hloops)


# ------------------------------------------------------------------------------------------- operators
def _edges(tris: np.ndarray):
    e = np.vstack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    e.sort(1)
    ue, inv, cnt = np.unique(e, axis=0, return_inverse=True, return_counts=True)
    return ue, inv.reshape(-1), cnt


def boundary_edges(tris: np.ndarray) -> np.ndarray:
    """Directed boundary edges (consistent with triangle CCW orientation)."""
    e = np.vstack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    key = np.sort(e, 1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    return e[cnt[inv.reshape(-1)] == 1]


def cotan_bending_matrix(xy: np.ndarray, tris: np.ndarray) -> sp.csr_matrix:
    """Q = K^T diag(1/A) K with K the cotan Laplacian rows of interior nodes (isometric bending energy)."""
    n = len(xy)
    I, J, W = [], [], []
    area = np.zeros(n)
    for k in range(3):
        i, j, o = tris[:, k], tris[:, (k + 1) % 3], tris[:, (k + 2) % 3]
        u, v = xy[i] - xy[o], xy[j] - xy[o]
        cot = (u * v).sum(1) / np.abs(u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0])
        I += [i, j]; J += [j, i]; W += [0.5 * cot, 0.5 * cot]
    a, b, c = xy[tris[:, 0]], xy[tris[:, 1]], xy[tris[:, 2]]
    At = 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
    for k in range(3):
        np.add.at(area, tris[:, k], At / 3)
    I, J, W = np.concatenate(I), np.concatenate(J), np.concatenate(W)
    Wm = sp.coo_matrix((W, (I, J)), shape=(n, n)).tocsr()
    L = sp.diags(np.asarray(Wm.sum(1)).ravel()) - Wm
    bnd = np.unique(boundary_edges(tris))
    interior = np.setdiff1d(np.arange(n), bnd)
    K = L[interior]
    return (K.T @ sp.diags(1.0 / area[interior]) @ K).tocsr()


# ------------------------------------------------------------------------------------------ relaxation
@dataclass
class Canopy3D:
    """Inflated canopy: nodes (N,3) [m], tris (M,3), attach ids, slit loops, payload anchors, diagnostics."""
    X: np.ndarray
    tris: np.ndarray
    attach: np.ndarray
    slit_loops: list
    anchors: np.ndarray        # (k,3) payload anchor points (line ends)
    flat: FlatMesh
    info: dict

    # ---- derived quantities
    def projected_area(self) -> float:
        """Area projected on the plane normal to the canopy axis (z); slit openings excluded."""
        a, b, c = (self.X[self.tris[:, k], :2] for k in range(3))
        return float(0.5 * np.sum((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])))

    def surface_area(self) -> float:
        a, b, c = (self.X[self.tris[:, k]] for k in range(3))
        return float(0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum())

    def slit_openings(self) -> list[dict]:
        """Per slit: 3D opening area (|vector area| of the gap loop), area projected on xy, max gap."""
        out = []
        for sa, sb in self.slit_loops:
            loop = np.r_[sa, sb[::-1][1:-1]]
            P = self.X[loop]
            va = 0.5 * np.cross(P, np.roll(P, -1, 0)).sum(0)
            gap = np.linalg.norm(self.X[sa[1:-1]] - self.X[sb[1:-1]], axis=1) if len(sa) > 2 else np.zeros(1)
            out.append({"area_3d_m2": float(np.linalg.norm(va)), "area_proj_m2": float(abs(va[2])),
                        "max_gap_m": float(gap.max())})
        return out

    def centroid(self) -> np.ndarray:
        a, b, c = (self.X[self.tris[:, k]] for k in range(3))
        w = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
        return ((a + b + c) / 3 * w[:, None]).sum(0) / w.sum()

    def hole_openings_proj(self) -> float:
        """Total open area of the cut-outs projected on the plane normal to the canopy axis."""
        tot = 0.0
        for ids in getattr(self.flat, "hole_loops", []):
            P = self.X[ids, :2]
            tot += abs(0.5 * float(np.dot(P[:, 0], np.roll(P[:, 1], -1)) - np.dot(np.roll(P[:, 0], -1), P[:, 1])))
        return tot

    def summary(self) -> dict:
        Ap = self.projected_area()
        so = self.slit_openings()
        slit_proj = sum(s["area_proj_m2"] for s in so)
        hole_proj = self.hole_openings_proj()
        open_proj = slit_proj + hole_proj
        z = self.X[:, 2]
        return {"projected_area_m2": Ap, "projected_diameter_m": math.sqrt(4 * Ap / math.pi),
                "surface_area_m2": self.surface_area(), "slit_open_area_proj_m2": slit_proj,
                "hole_open_area_proj_m2": hole_proj,
                "slit_open_area_3d_m2": sum(s["area_3d_m2"] for s in so),
                "porosity_proj": open_proj / (Ap + open_proj) if open_proj > 0 else 0.0,
                "max_slit_gap_m": max([s["max_gap_m"] for s in so], default=0.0),
                "height_m": float(z.max() - z[self.attach].mean()),
                "apex_above_anchors_m": float(z.max() - self.anchors[:, 2].mean()), "centroid_m": self.centroid().tolist(), **self.info}


def form_find(design: Design, cfg: dict | None = None, *, h: float = 0.004, pressure: float | None = None,
              Et: float = 2.0e3, bend: float = 8.3e-5, line_EA: float = 500.0, line_length: float | None = None,
              attach: str = "geometry", method: str = "fire", max_iter: int = 40000, tol: float = 2e-3,
              comp: float = 5e-4, verbose: bool = False, flutter_avg: int | None = None) -> Canopy3D:
    """Inflate a canopy design by dynamic relaxation.

    Sheet (assumption, L2): generic 0.1 mm plastic, E ~ 1 GPa -> bending B = E t^3/12 = 8.3e-5 N m.
    In-plane E*t (physically ~1e5 N/m) is capped at Et = 2 kN/m for relaxation speed: strains stay < 1 %
    and the shape is insensitive to Et above ~1 kN/m (checked). Lines: one per payload anchor
    (chutesim.payload.anchors_m, fixed points, payload hangs below), attached at the geometry attach
    points (cfg attach_inset_m, like the real build; attach='rim' uses the outline at the line azimuths).
    comp: compressive stiffness as a fraction of Et (5e-4 -> ~1 N/m): residual stiffness of the wrinkled
    sheet; regularises the tension-only switching so the relaxation converges (comp = 0 chatters).
    tol: RMS residual force on membrane nodes relative to the nodal pressure force.
    """
    from chutesim.cutouts import build_any_geometry
    from chutesim.geometry import boundary_radius
    from chutesim.payload import anchors_m, line_angles
    cfg = cfg or load_config()
    g = build_any_geometry(design, cfg)
    rho = float(cfg["physics"]["rho"])
    p = 0.5 * rho * 7.0**2 if pressure is None else float(pressure)
    Lline = float(cfg["canopy"]["line_length_m"]) if line_length is None else float(line_length)
    ang = line_angles(cfg)
    if attach == "rim":
        apts = np.array([[boundary_radius(g.outline, a) * math.cos(a), boundary_radius(g.outline, a) * math.sin(a)] for a in ang])
    else:
        apts = g.attach_points
    anchors = anchors_m(cfg)
    if len(anchors) != len(apts):
        raise ValueError(f"{len(anchors)} payload anchors vs {len(apts)} line attach points")
    # pair each attach point with the anchor closest in azimuth
    aa = np.arctan2(anchors[:, 1], anchors[:, 0])
    pa = np.arctan2(apts[:, 1], apts[:, 0])
    order = [int(np.argmin(np.abs(np.angle(np.exp(1j * (aa - t)))))) for t in pa]
    # cuts shorter than h/4 are below mesh resolution (and physically negligible): not cut
    slits = g.slits[np.linalg.norm(g.slits[:, 1] - g.slits[:, 0], axis=1) >= 0.25 * h] if len(g.slits) else g.slits
    fm = mesh_flat(g.outline, slits, apts, h, holes=getattr(g, "holes", []))
    from chutesim.freeform import FreeDesign
    if flutter_avg is None:  # free-form canopies: average a fluttering shape instead of running 40k iterations
        flutter_avg = 16 if isinstance(design, FreeDesign) else 0
    if flutter_avg and max_iter == 40000:
        max_iter = 12000
    return relax(fm, anchors[order], p=p, Et=Et, bend=bend, line_EA=line_EA, Lline=Lline, method=method,
                 max_iter=max_iter, tol=tol, comp=comp, verbose=verbose, flutter_avg=flutter_avg,
                 extra={"design": dict(q=design.q, slit_len=design.slit_len, slit_r=design.slit_r,
                                       **(design.key_extra() if hasattr(design, "key_extra") else {})),
                        "n_holes": len(getattr(g, "holes", [])), "n_lines": len(apts), "n_slits": len(g.slits), "n_slits_cut": len(slits), "mesh_h_m": h})


def relax(fm: FlatMesh, anchors: np.ndarray, *, p: float, Et: float, bend: float, line_EA: float, Lline: float,
          method: str = "fire", max_iter: int = 40000, tol: float = 2e-3, comp: float = 0.0,
          shape_tol: float = 5e-5, verbose: bool = False, extra: dict | None = None,
          flutter_avg: int = 0) -> Canopy3D:
    """Explicit relaxation to static equilibrium. method: 'fire' (FIRE, Bitzek 2006, mass-preconditioned)
    or 'kd' (Barnes kinetic damping). Fixed anchors (k,3), one line per fm.attach node.
    flutter_avg > 0: if not converged at max_iter, return the mean of the last flutter_avg shape snapshots
    (taken every 250 iterations) and report the flutter amplitude (max node standard deviation); free flaps
    of free-form canopies keep oscillating in the quasi-static model instead of settling."""
    xy, tris = fm.xy, fm.tris
    n = len(xy)
    B = float(bend)
    edges, _, _ = _edges(tris)
    ne = len(edges)
    L0 = np.linalg.norm(xy[edges[:, 0]] - xy[edges[:, 1]], axis=1)
    a, b, c = xy[tris[:, 0]], xy[tris[:, 1]], xy[tris[:, 2]]
    At = 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
    e3 = np.sort(np.vstack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), 1)
    _, inv = np.unique(e3, axis=0, return_inverse=True)
    Ae = np.bincount(inv.reshape(-1), weights=np.tile(At, 3), minlength=ne)
    ke = Et * Ae / L0**2                       # edge spring stiffness [N/m]
    Q = cotan_bending_matrix(xy, tris)
    att = fm.attach
    anchors = np.asarray(anchors, float)
    k_line = line_EA / Lline
    dh = np.linalg.norm(xy[att] - anchors[:, :2], axis=1)
    z0 = anchors[:, 2].max() + math.sqrt(max(Lline**2 - dh.max()**2, 1e-6))
    X = np.column_stack([xy, np.full(n, z0)])

    Dm = sp.csr_matrix((np.r_[np.ones(ne), -np.ones(ne)], (np.r_[edges[:, 0], edges[:, 1]], np.r_[np.arange(ne), np.arange(ne)])), shape=(n, ne))
    Tm = sp.csr_matrix((np.ones(3 * len(tris)), (tris.T.ravel(), np.tile(np.arange(len(tris)), 3))), shape=(n, len(tris)))
    Am = sp.csr_matrix((np.ones(len(att)), (att, np.arange(len(att)))), shape=(n, len(att)))
    ia, ib, t0, t1, t2 = edges[:, 0], edges[:, 1], tris[:, 0], tris[:, 1], tris[:, 2]

    def forces(X):
        d = X[ib] - X[ia]
        L = np.sqrt((d * d).sum(1))
        e = L - L0
        T = ke * np.where(e > 0, e, comp * e)            # tension only (wrinkling sheet)
        F = Dm @ ((T / L)[:, None] * d)
        F -= B * (Q @ X)
        F += Tm @ ((p / 6.0) * np.cross(X[t1] - X[t0], X[t2] - X[t0]))   # follower pressure
        dl = X[att] - anchors
        ll = np.sqrt((dl * dl).sum(1))
        Tl = k_line * np.maximum(ll - Lline, 0.0)
        F -= Am @ ((Tl / ll)[:, None] * dl)
        return F, Tl

    S = np.asarray(abs(Dm) @ ke).ravel() + 2 * B * np.abs(Q).sum(1).A1
    S[att] += k_line
    m = S[:, None]
    F_ext = p * At.sum() / n
    free = np.setdiff1d(np.arange(n), att)

    def resid(F):
        return float(np.sqrt((F[free] ** 2).sum(1).mean()) / F_ext)

    V = np.zeros_like(X)
    dt, dtmax, alpha, npos, KEp = 0.2, 1.0, 0.1, 0, 0.0
    hist = []
    it = 0
    res = np.inf
    Xprev = None
    dX = np.inf
    snaps = []
    for it in range(1, max_iter + 1):
        F, Tl = forces(X)
        if method == "fire":
            P = float((F * V).sum())
            if P > 0:
                vn, fn = np.sqrt((V * V).sum()), np.sqrt((F * F).sum())
                V = (1 - alpha) * V + alpha * vn * F / max(fn, 1e-30)
                npos += 1
                if npos > 5:
                    dt, alpha = min(dt * 1.1, dtmax), alpha * 0.99
            else:
                X -= 0.5 * dt * V
                V[:] = 0.0
                dt, alpha, npos = dt * 0.5, 0.1, 0
            V += dt * F / m
            X += dt * V
        else:
            V += F / m
            X += V
            KE = float((m * V**2).sum())
            if KE < KEp:
                X -= 1.5 * V
                V[:] = 0.0
                KE = 0.0
            KEp = KE
        if it % 250 == 0:
            res = resid(F)
            dX = float(np.abs(X - Xprev).max()) if Xprev is not None else np.inf
            Xprev = X.copy()
            hist.append((it, res, dX))
            if flutter_avg:
                snaps = (snaps + [X.copy()])[-flutter_avg:]
            if verbose:
                print(f"it {it} res {res:.2e} dX {dX:.1e} dt {dt:.2f} line T {Tl.mean():.4f} N")
            # converged: force residual small, or shape stationary (max nodal move over 250 its < shape_tol)
            if res < tol or (it > 4000 and dX < shape_tol):
                break
    converged = bool(res < tol or dX < shape_tol)
    flutter = {}
    if not converged and flutter_avg and len(snaps) >= 2:
        S_ = np.array(snaps)
        X = S_.mean(0)
        flutter = {"flutter_averaged": True, "flutter_snapshots": len(snaps),
                   "flutter_amp_m": float(np.linalg.norm(S_.std(0), axis=1).max())}
    F, Tl = forces(X)
    res = resid(F)
    strain = np.linalg.norm(X[ib] - X[ia], axis=1) / L0 - 1
    info = {"iterations": it, "residual_rel": res, "shape_change_m": dX, **flutter,
            "converged": converged, "method": method, "comp": comp,
            "pressure_Pa": p, "Et_N_per_m": Et, "bend_Nm": B, "line_EA_N": line_EA, "line_length_m": Lline,
            "line_tension_N": Tl.tolist(), "max_strain": float(strain.max()), "n_nodes": n,
            "n_tris": len(tris), "slack_lines": int((Tl <= 0).sum()), "residual_history": hist, **(extra or {})}
    return Canopy3D(X, tris, att, fm.slit_loops, anchors, fm, info)


# --------------------------------------------------------------------------------------------- export
def vertex_normals(X: np.ndarray, tris: np.ndarray) -> np.ndarray:
    fn = np.cross(X[tris[:, 1]] - X[tris[:, 0]], X[tris[:, 2]] - X[tris[:, 0]])
    vn = np.zeros_like(X)
    for k in range(3):
        np.add.at(vn, tris[:, k], fn)
    return vn / np.linalg.norm(vn, axis=1, keepdims=True)


def solid_shell(X: np.ndarray, tris: np.ndarray, thickness: float = 1e-3):
    """Closed thin solid: surface offset by +/- t/2 along vertex normals, boundary (rim + slit) walls stitched."""
    n = len(X)
    vn = vertex_normals(X, tris)
    top = X + 0.5 * thickness * vn
    bot = X - 0.5 * thickness * vn
    V = np.vstack([top, bot])
    F = [tris, tris[:, ::-1] + n]
    be = boundary_edges(tris)                       # directed a->b as in top faces
    a, b = be[:, 0], be[:, 1]
    F.append(np.column_stack([b, a, a + n]))
    F.append(np.column_stack([b, a + n, b + n]))
    return V, np.vstack(F)


def write_stl(path, V: np.ndarray, F: np.ndarray, name: str = "canopy") -> None:
    """ASCII STL with a single solid region `name`."""
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-30)
    with open(path, "w") as f:
        f.write(f"solid {name}\n")
        for nn, tri in zip(fn, F):
            f.write(f" facet normal {nn[0]:.6e} {nn[1]:.6e} {nn[2]:.6e}\n  outer loop\n")
            for v in V[tri]:
                f.write(f"   vertex {v[0]:.8e} {v[1]:.8e} {v[2]:.8e}\n")
            f.write("  endloop\n endfacet\n")
        f.write(f"endsolid {name}\n")


def write_canopy_stl(c: Canopy3D, path, solid: bool = True, thickness: float = 1e-3) -> None:
    """Write the canopy as a closed thin solid (default) or as the zero-thickness surface (for baffles)."""
    if solid:
        V, F = solid_shell(c.X, c.tris, thickness)
    else:
        V, F = c.X, c.tris
    write_stl(path, V, F)


# --------------------------------------------------------------------------------------------- render
def render(c: Canopy3D, path, title: str = "", lines: bool = True, elev: float = -28, azim: float = -60,
           dpi: int = 150, zoom_slit: bool = False) -> None:
    """Shaded 3D render (Lambert + specular-ish), rim and slit edges outlined; side panel with lines."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection

    X = c.X - np.array([0, 0, c.X[:, 2].max()])  # apex at z=0 for the main view
    tri = X[c.tris]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    fn /= np.linalg.norm(fn, axis=1, keepdims=True)
    light = np.array([-0.4, -0.6, -0.7]); light /= np.linalg.norm(light)
    lam = np.abs(fn @ light)
    base = np.array([0.93, 0.42, 0.12])
    inside = (fn[:, 2] < 0)
    col = np.clip(base[None] * (0.35 + 0.65 * lam[:, None]), 0, 1)
    col[inside] = np.clip(np.array([0.98, 0.6, 0.3]) * (0.35 + 0.65 * lam[inside, None]), 0, 1)
    be = boundary_edges(c.tris)

    ncols = 2 if lines else 1
    fig = plt.figure(figsize=(6.2 * ncols, 5.6))
    ax = fig.add_subplot(1, ncols, 1, projection="3d")
    ax.add_collection3d(Poly3DCollection(tri, facecolors=col, edgecolors="none", linewidths=0, antialiased=False))
    ax.add_collection3d(Line3DCollection(X[be], colors="k", linewidths=0.8))
    r = np.abs(X[:, :2]).max() * 1.05
    if zoom_slit and c.slit_loops:
        sa, sb = c.slit_loops[0]
        cen = X[np.r_[sa, sb]].mean(0)
        s = max(np.ptp(X[np.r_[sa, sb]], axis=0).max(), 0.01) * 0.9
        ax.set_xlim(cen[0] - s, cen[0] + s); ax.set_ylim(cen[1] - s, cen[1] + s); ax.set_zlim(cen[2] - s, cen[2] + s)
    else:
        zmin = X[:, 2].min()
        ax.set_xlim(-r, r); ax.set_ylim(-r, r); ax.set_zlim(zmin - (2 * r + zmin) / 2 + zmin / 2, zmin + 2 * r)
        ax.set_zlim(-0.85 * r, 0.05 * r)
    ax.set_box_aspect((1, 1, 0.45) if not zoom_slit else (1, 1, 1), zoom=1.25)
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    ax.text2D(0.02, 0.02, f"span {2 * np.abs(X[:, :2]).max() * 100:.1f} cm", transform=ax.transAxes, fontsize=8)
    ax.text2D(0.5, 0.97, "inflated canopy, view from below into the mouth", transform=ax.transAxes,
              fontsize=10, ha="center")
    if lines:
        ax2 = fig.add_subplot(1, 2, 2)
        Y = c.X
        tri2 = Y[c.tris]
        ax2.tripcolor(Y[:, 0], Y[:, 2], c.tris, facecolors=np.zeros(len(c.tris)), cmap="Oranges", alpha=0.0)
        from matplotlib.collections import PolyCollection
        ax2.add_collection(PolyCollection(tri2[:, :, [0, 2]], facecolors=(0.93, 0.42, 0.12, 0.25), edgecolors="none"))
        ax2.plot(*Y[be][:, :, [0, 2]].transpose(2, 1, 0), color="0.2", lw=0.5)
        for i, an in zip(c.attach, c.anchors):
            ax2.plot([Y[i, 0], an[0]], [Y[i, 2], an[2]], color="0.35", lw=0.7)
        ax2.plot(c.anchors[:, 0], c.anchors[:, 2], "ko", ms=3)
        ax2.add_patch(__import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle(
            (-0.045, c.anchors[:, 2].mean() - 0.02), 0.09, 0.02, color="0.5", alpha=0.6))
        ax2.annotate("payload anchors", (c.anchors[:, 0].max(), c.anchors[:, 2].mean()), (0.05, 0.0), fontsize=8)
        ax2.annotate("", (0.11, Y[:, 2].min() - 0.06), (0.11, Y[:, 2].min() - 0.16),
                     arrowprops=dict(arrowstyle="->", color="tab:blue", lw=1.5))
        ax2.text(0.115, Y[:, 2].min() - 0.13, "relative\nairflow", color="tab:blue", fontsize=8)
        ax2.set_aspect("equal"); ax2.set_xlim(-0.15, 0.17); ax2.set_ylim(-0.03, Y[:, 2].max() + 0.03)
        ax2.set_xlabel("x [m]"); ax2.set_ylabel("z [m]"); ax2.set_title("side view with suspension lines", fontsize=10)
        ax2.grid(alpha=0.3)
    s = c.summary()
    txt = (f"projected area {s['projected_area_m2']*1e4:.0f} cm$^2$ (flat 250 cm$^2$)   "
           f"height {s['height_m']*100:.1f} cm   slit opening {s['slit_open_area_proj_m2']*1e4:.2f} cm$^2$")
    fig.suptitle((title + "\n" if title else "") + txt, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
