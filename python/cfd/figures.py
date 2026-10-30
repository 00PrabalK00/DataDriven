"""Slide figures (150 dpi) under results/cfd/figures/: canopy renders, slit close-up, flow-field slice.

Usage: python -m cfd.figures shapes        (renders of 3 designs + slit close-up)
       python -m cfd.figures flow <log_dir_with_postProcessing> <alpha_deg> <out.png>
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

from chutesim.config import load_config
from chutesim.geometry import Design

REPO = Path(__file__).resolve().parents[2]
FIG = REPO / "results" / "cfd" / "figures"
DESIGNS = {"circle_q2_l0": (Design(2.0, 0.0, 0.45), "circle, no slits (q=2, l=0)"),
           "mid_q5_l008_r045": (Design(5.0, 0.08, 0.45), "mid design (q=5, l=0.08, r=0.45)"),
           "square_q8_l015_r045": (Design(8.0, 0.15, 0.45), "rounded square with slits (q=8, l=0.15, r=0.45)")}


def shapes() -> list[Path]:
    from .formfind import render
    from .shapes import get_shape
    cfg = load_config()
    FIG.mkdir(parents=True, exist_ok=True)
    out = []
    for name, (d, title) in DESIGNS.items():
        c = get_shape(d, cfg)
        p = FIG / f"canopy_{name}.png"
        render(c, p, title=title)
        out.append(p)
        if d.slit_len > 0:
            p2 = FIG / f"slit_closeup_{name}.png"
            slit_closeup(c, p2, title)
            out.append(p2)
    return out


def slit_closeup(c, path, title: str) -> None:
    """Close-up of one slit: shaded surface patch around the slit, gap loop filled, seen along the axis."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection
    from .formfind import boundary_edges
    sa, sb = c.slit_loops[0]
    X = c.X
    cen = X[np.r_[sa, sb]].mean(0)
    L = np.linalg.norm(X[sa[-1]] - X[sa[0]])
    s = 1.3 * L
    tc = X[c.tris].mean(1)
    sel = np.linalg.norm(tc - cen, axis=1) < 1.6 * s
    tri = X[c.tris[sel]]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    fn /= np.linalg.norm(fn, axis=1, keepdims=True)
    light = np.array([-0.3, -0.5, -0.8]); light /= np.linalg.norm(light)
    col = np.clip(np.array([0.93, 0.42, 0.12]) * (0.35 + 0.65 * np.abs(fn @ light))[:, None], 0, 1)
    loop = np.r_[sa, sb[::-1][1:-1]]
    fig = plt.figure(figsize=(11, 4.8))
    ax = fig.add_subplot(1, 2, 1)
    for k, (a_, b_) in enumerate(c.slit_loops):
        r = np.linalg.norm(X[a_[1:-1], :2] - X[a_[0], :2], axis=1) * 1000
        gap = np.linalg.norm(X[a_[1:-1]] - X[b_[1:-1]], axis=1) * 1000
        ax.plot(np.r_[0, r, L * 1000], np.r_[0, gap, 0], "-o", ms=2, lw=1, label=f"slit {k + 1}")
    ax.set_xlabel("position along slit [mm]"); ax.set_ylabel("gap between cut edges [mm]")
    ax.set_title("slit gap after inflation (all slits)", fontsize=10); ax.grid(alpha=0.3); ax.legend(fontsize=7)
    ax2 = fig.add_subplot(1, 2, 2)
    P = X[c.tris[sel]][:, :, :2] * 1000
    ax2.add_collection(PolyCollection(P, facecolors=(0.93, 0.42, 0.12, 0.35), edgecolors=(0.4, 0.2, 0.05, 0.4), linewidths=0.3))
    G = X[loop][:, :2] * 1000
    ax2.fill(G[:, 0], G[:, 1], color="tab:blue", alpha=0.8, label="opening (flow passage)")
    ax2.plot(*X[sa][:, :2].T * 1000, "k-", lw=1); ax2.plot(*X[sb][:, :2].T * 1000, "k-", lw=1)
    so = c.slit_openings()[0]
    ax2.set_xlim(cen[0] * 1000 - 0.7 * s * 1000, cen[0] * 1000 + 0.7 * s * 1000)
    ax2.set_ylim(cen[1] * 1000 - 0.7 * s * 1000, cen[1] * 1000 + 0.7 * s * 1000)
    ax2.set_aspect("equal"); ax2.set_xlabel("x [mm]"); ax2.set_ylabel("y [mm]"); ax2.legend(fontsize=8, loc="upper left")
    ax2.set_title(f"projected along the flow: opening {so['area_proj_m2']*1e6:.0f} mm$^2$, max gap {so['max_gap_m']*1000:.1f} mm",
                  fontsize=10)
    ax2.grid(alpha=0.3)
    fig.suptitle(title + f" - cut length {L*1000:.0f} mm (cut, zero width when flat)", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _read_raw(path: Path):
    """OpenFOAM raw surface file: header '# x y z f...' then rows."""
    names = None
    rows = []
    for line in open(path):
        if line.startswith("#"):
            t = line[1:].split()
            if t and t[0] == "x":
                names = t
            continue
        if line.strip():
            rows.append([float(v) for v in line.split()])
    return names, np.array(rows)


def read_vtk_polydata(path: Path):
    """Legacy ASCII VTK polydata: points (N,3), polygons (list of index arrays), first CELL_DATA field."""
    tok = open(path).read().split()
    i = tok.index("POINTS")
    n = int(tok[i + 1])
    P = np.array(tok[i + 3:i + 3 + 3 * n], float).reshape(n, 3)
    i = tok.index("POLYGONS")
    m, size = int(tok[i + 1]), int(tok[i + 2])
    flat = np.array(tok[i + 3:i + 3 + size], int)
    polys, k = [], 0
    for _ in range(m):
        c = flat[k]
        polys.append(flat[k + 1:k + 1 + c])
        k += c + 1
    i = tok.index("CELL_DATA")
    j = i + 4  # CELL_DATA m FIELD FieldData 1 <name> 1 m float
    j = tok.index("float", i) + 1
    val = np.array(tok[j:j + m], float)
    return P, polys, val


def flow(log_dir: Path, alpha_deg: float, out: Path, center, title: str = "") -> Path:
    """Two panels: |U| on the y=0 plane with in-plane streamlines; Cp on the canopy (view from below)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from scipy.interpolate import griddata
    log_dir = Path(log_dir)
    tdir = sorted((log_dir / "postProcessing" / "planes").iterdir(), key=lambda p: float(p.name))[-1]
    _, d = _read_raw(tdir / "U_midY.raw")
    x, z, Ux, Uz = d[:, 0], d[:, 2], d[:, 3], d[:, 5]
    cx, cz = float(center[0]), float(center[2])
    D = 0.178
    xi = np.linspace(cx - 1.3 * D, cx + 1.3 * D, 260)
    zi = np.linspace(cz - 1.2 * D, cz + 3.0 * D, 420)
    XI, ZI = np.meshgrid(xi, zi)
    m = (np.abs(x - cx) < 1.6 * D) & (z > cz - 1.5 * D) & (z < cz + 3.3 * D)
    gx = griddata((x[m], z[m]), Ux[m], (XI, ZI), method="linear")
    gz = griddata((x[m], z[m]), Uz[m], (XI, ZI), method="linear")
    P, polys, pval = read_vtk_polydata(sorted((log_dir / "postProcessing" / "canopyP").glob("*/canopy.vtk"))[-1])
    q = 0.5 * 7.0**2                                   # kinematic p / (0.5 U^2) = Cp
    cp = pval / q
    fig, axs = plt.subplots(1, 3, figsize=(16, 6.2), gridspec_kw={"width_ratios": [1, 1, 1]})
    ax = axs[0]
    sp = np.hypot(gx, gz)
    im = ax.pcolormesh((XI - cx) / D, (ZI - cz) / D, sp, cmap="viridis", shading="auto", vmin=0, vmax=9)
    ax.streamplot((xi - cx) / D, (zi - cz) / D, np.nan_to_num(gx), np.nan_to_num(gz), color="w",
                  linewidth=0.5, density=1.5, arrowsize=0.6)
    sec = np.abs(P[:, 1]) < 0.004
    ax.plot((P[sec, 0] - cx) / D, (P[sec, 2] - cz) / D, ".", color="orangered", ms=2.5, label="canopy section")
    a = np.radians(alpha_deg)
    ax.annotate("", (-1.0 + 0.35 * np.sin(a), -0.75 + 0.35 * np.cos(a)), (-1.0, -0.75),
                arrowprops=dict(arrowstyle="->", color="w", lw=2))
    ax.text(-1.25, -0.95, "U = 7 m/s", color="w", fontsize=9)
    fig.colorbar(im, ax=ax, shrink=0.75, label="|U| in plane y = 0 [m/s]")
    ax.set_aspect("equal"); ax.set_xlabel("x / D"); ax.set_ylabel("z / D")
    ax.set_title("velocity magnitude + streamlines (y = 0)", fontsize=10)
    ax.legend(loc="upper right", fontsize=8, markerscale=3)
    # patch normals point out of the fluid: +z -> fluid below -> inner (mouth) face
    nz = np.array([np.cross(P[pp[1]] - P[pp[0]], P[pp[2]] - P[pp[0]])[2] for pp in polys])
    for axk, sel, ttl in ((axs[1], nz > 0, "Cp, inner face (mouth, facing the flow)"),
                          (axs[2], nz <= 0, "Cp, outer face (wake side)")):
        idx = np.where(sel)[0]
        pc = PolyCollection([P[polys[i]][:, :2] * 1000 for i in idx], array=cp[idx], cmap="RdBu_r",
                            edgecolors="none")
        pc.set_clim(-1.5, 1.5)
        axk.add_collection(pc)
        axk.set_xlim(P[:, 0].min() * 1000 - 5, P[:, 0].max() * 1000 + 5)
        axk.set_ylim(P[:, 1].min() * 1000 - 5, P[:, 1].max() * 1000 + 5)
        axk.set_aspect("equal"); axk.set_xlabel("x [mm]"); axk.set_ylabel("y [mm]")
        axk.set_title(ttl, fontsize=10)
    fig.colorbar(pc, ax=list(axs[1:]), shrink=0.75, label="Cp = p / (0.5 rho U$^2$)")
    fig.suptitle(title or f"Canopy q=8, l=0.15, r=0.45 - RANS k-omega SST, U = 7 m/s, alpha = {alpha_deg:g} deg "
                 "(coarse laptop mesh)", fontsize=11)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


if __name__ == "__main__":
    if sys.argv[1] == "shapes":
        for p in shapes():
            print(p)
    elif sys.argv[1] == "flow":
        c = [float(v) for v in sys.argv[5].split(",")]
        print(flow(Path(sys.argv[2]), float(sys.argv[3]), Path(sys.argv[4]), c))
