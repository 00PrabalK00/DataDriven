"""Free-form canopies: outline AND holes from one smooth material field (level-set encoding).

phi(x, y) = 1 - (r / R_eq)^2 + sum_i w_i * exp(-|p - c_i|^2 / (2 sigma^2))
with Gaussian bumps c_i on a hexagonal grid (spacing 0.35 R_eq, 4 rings, 61 centres). Plastic is where
phi > t; the threshold t is chosen so the main piece has exactly A0 = 250 cm^2 of plastic (holes count as
removed material). Positive weights add material, negative ones carve holes or notches, so any outline
and any number/shape of holes can appear: nothing is prescribed. Symmetry (optional): 'D6' (6-fold +
mirror, matches the 6 lines; 10 weights), 'C6' (6-fold; 11), 'D3' (3-fold + mirror; 18), 'none' (61).

Fabrication rules (feasibility): one piece; holes smaller than min_hole_m2 are filled (cannot be cut
reliably); no plastic bridge thinner than min_bridge_m; solid patches at the 6 line attachment points.
Kept separate from geometry.py so simulator provenance hashes of existing designs are unchanged.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from .geometry import Design, Geometry, boundary_radius, polygon_area

SPACING = 0.35      # bump spacing / R_eq
RINGS = 4
SIGMA = 0.6         # bump width / spacing
GRID = 281          # field samples per side over [-1.7, 1.7] R_eq
EXTENT = 1.7


@dataclass
class FreeDesign(Design):
    weights: tuple = ()
    sym: str = "D6"

    def key_extra(self) -> dict:
        return {"free": [float(w) for w in self.weights], "sym": self.sym, "freeform_src": source_hash()}


def source_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


def free_design(weights, sym: str = "D6") -> FreeDesign:
    return FreeDesign(0.0, 0.0, 0.45, None, tuple(float(w) for w in weights), sym)


@lru_cache(maxsize=8)
def centres_and_orbits(sym: str):
    """Hex-grid bump centres (units of R_eq) and, per free weight, the indices of the centres it drives."""
    pts = []
    for i in range(-RINGS, RINGS + 1):
        for j in range(-RINGS, RINGS + 1):
            k = -i - j
            if max(abs(i), abs(j), abs(k)) <= RINGS:
                pts.append([SPACING * (i + 0.5 * j), SPACING * j * math.sqrt(3) / 2])
    C = np.array(pts)
    if sym == "none":
        return C, [np.array([i]) for i in range(len(C))]
    n, mirror = {"D6": (6, True), "C6": (6, False), "D3": (3, True)}[sym]
    seen, orbits = -np.ones(len(C), int), []
    for i, p in enumerate(C):
        if seen[i] >= 0:
            continue
        imgs = []
        for k in range(n):
            a = 2 * math.pi * k / n
            R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
            q = R @ p
            imgs.append(q)
            if mirror:
                imgs.append(np.array([q[0], -q[1]]))
        idx = sorted({int(np.argmin(np.linalg.norm(C - q, axis=1))) for q in imgs})
        seen[idx] = len(orbits)
        orbits.append(np.array(idx))
    return C, orbits


def n_weights(sym: str) -> int:
    return len(centres_and_orbits(sym)[1])


def field(weights, sym: str, R_eq: float):
    C, orbits = centres_and_orbits(sym)
    w = np.zeros(len(C))
    for wk, idx in zip(weights, orbits):
        w[idx] = wk
    s = np.linspace(-EXTENT, EXTENT, GRID)
    X, Y = np.meshgrid(s, s)
    sig = SIGMA * SPACING
    phi = 1.0 - X**2 - Y**2
    for (cx, cy), wi in zip(C, w):
        if wi != 0.0:
            phi += wi * np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2 * sig**2))
    return s * R_eq, phi


def _material(phi, t, px_area, min_hole_px):
    """Main connected piece of phi > t with small holes filled; returns (mask, net area)."""
    from scipy import ndimage
    lab, n = ndimage.label(phi > t)
    if n == 0:
        return None, 0.0
    sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
    m = lab == (1 + int(np.argmax(sizes)))
    voids, nv = ndimage.label(~m)
    for k in range(1, nv + 1):
        v = voids == k
        border = v[0].any() or v[-1].any() or v[:, 0].any() or v[:, -1].any()
        if not border and v.sum() < min_hole_px:
            m |= v
    return m, float(m.sum()) * px_area


def _polys(mask, s):
    """Outer boundary and hole polygons (metres) of a binary mask, from a lightly smoothed contour."""
    import contourpy
    from scipy import ndimage
    f = ndimage.gaussian_filter(mask.astype(float), 1.0)
    gen = contourpy.contour_generator(s, s, f, line_type="Separate")
    lines = [ln for ln in gen.lines(0.5) if len(ln) > 8 and np.allclose(ln[0], ln[-1])]
    if not lines:
        return None, []
    lines = [ln[:-1] for ln in lines]
    areas = [abs(polygon_area(ln)) for ln in lines]
    io = int(np.argmax(areas))
    outer = lines[io]
    if polygon_area(outer) < 0:
        outer = outer[::-1]
    from matplotlib.path import Path as MplPath
    op = MplPath(outer)
    holes = []
    for k, ln in enumerate(lines):
        if k != io and op.contains_point(ln.mean(0)):
            holes.append(ln[::-1] if polygon_area(ln) < 0 else ln)
    return outer, holes


def build_free_geometry(design: FreeDesign, cfg: dict, check: bool = True) -> Geometry:
    cc = cfg["canopy"]
    fb = cfg.get("freeform", {})
    A0 = float(cc["A0_m2"])
    R_eq = math.sqrt(A0 / math.pi)
    s, phi = field(design.weights, design.sym, R_eq)
    px = (s[1] - s[0]) ** 2
    min_hole_px = float(fb.get("min_hole_m2", 3e-5)) / px
    # bisection on the level: net plastic area of the main piece = A0
    srt = np.sort(phi.ravel())[::-1]
    n0 = int(A0 / px)
    lo, hi = float(srt[min(int(1.6 * n0), len(srt) - 1)]), float(srt[max(int(0.8 * n0), 0)])
    for _ in range(24):
        t = 0.5 * (lo + hi)
        _, a = _material(phi, t, px, min_hole_px)
        lo, hi = (t, hi) if a > A0 else (lo, t)
    mask, _ = _material(phi, 0.5 * (lo + hi), px, min_hole_px)
    outline, holes = _polys(mask, s)
    reasons = []
    if outline is None:
        outline = np.array([[R_eq, 0], [0, R_eq], [-R_eq, 0], [0, -R_eq]], float)
        reasons.append("no_shape")
    # exact net area: uniform scale (contour smoothing shifts the area by a fraction of a pixel)
    net = polygon_area(outline) - sum(polygon_area(h) for h in holes)
    k = math.sqrt(A0 / net)
    outline, holes = outline * k, [h * k for h in holes]
    from .payload import line_angles
    attach = np.array([[(boundary_radius(outline, t) - cc["attach_inset_m"]) * math.cos(t),
                        (boundary_radius(outline, t) - cc["attach_inset_m"]) * math.sin(t)] for t in line_angles(cfg)])
    area_holes = sum(polygon_area(h) for h in holes)
    g = Geometry(design, outline, np.zeros((0, 2, 2)), np.zeros(0), attach, A0, R_eq, float("nan"),
                 polygon_area(outline), area_holes)
    g.holes = holes
    g.mask_info = {"pixel_m": float(s[1] - s[0]) * k}
    if check:
        reasons += check_free(g, mask, k * (s[1] - s[0]), cc, fb)
        g.feasible, g.reasons = (len(reasons) == 0), reasons
    return g


def check_free(g: Geometry, mask, px_m: float, cc: dict, fb: dict) -> list:
    from matplotlib.path import Path as MplPath
    from scipy import ndimage
    from scipy.spatial.distance import cdist
    reasons = []
    if abs(g.area_net - g.A0) > 1e-9:
        reasons.append("net_area_violation")
    # thinnest bridge: opening with a disc of diameter min_bridge must not split the piece or lose much area
    r_px = max(int(round(0.5 * cc["min_bridge_m"] / px_m)), 1)
    yy, xx = np.mgrid[-r_px:r_px + 1, -r_px:r_px + 1]
    disc = xx**2 + yy**2 <= r_px**2
    opened = ndimage.binary_opening(mask, structure=disc)
    _, n = ndimage.label(opened)
    if n > 1 or opened.sum() < (1 - fb.get("max_thin_frac", 0.03)) * mask.sum():
        reasons.append("bridge_too_thin")
    # line attachment points (attach_inset_m inside the rim, as in the build): inside the plastic, and no hole
    # closer than the reinforcement patch radius + a bridge (same rule as slits in geometry.check_feasible)
    op = MplPath(g.outline)
    clear = cc["attach_patch_radius_m"] + cc["min_bridge_m"]
    if not op.contains_points(g.attach_points).all() or any(
            MplPath(h).contains_points(g.attach_points).any() or cdist(g.attach_points, h).min() < clear for h in g.holes):
        reasons.append("hole_at_line_attachment")
    span = 2 * np.abs(g.outline).max()
    if span > fb.get("max_span_m", 0.30):
        reasons.append("too_large_for_sheet")
    return reasons


def free_features(g: Geometry) -> dict:
    """Generic shape features for surrogates (same meaning for any design family)."""
    from .geometry import polygon_perimeter
    P = polygon_perimeter(g.outline)
    rad = np.linalg.norm(g.outline, axis=1)
    areas = np.array([polygon_area(h) for h in g.holes]) if g.holes else np.zeros(0)
    radii = np.array([np.linalg.norm(h.mean(0)) for h in g.holes]) if g.holes else np.zeros(0)
    return {"c_iso": 4 * math.pi * g.area_outline / P**2, "max_radius_norm": float(rad.max() / g.R_eq),
            "outline_radius_norm": float(np.sqrt(np.mean(rad**2)) / g.R_eq),
            "open_frac": float(areas.sum() / g.area_outline), "n_holes": int(len(areas)),
            "open_r_norm": float((areas * radii).sum() / areas.sum() / g.R_eq) if len(areas) else 0.0,
            "open_perimeter_norm": float(sum(polygon_perimeter(h) for h in g.holes) / g.R_eq)}
