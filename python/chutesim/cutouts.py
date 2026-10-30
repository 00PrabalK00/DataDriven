"""Cut-outs (geometric porosity): canopies with a central vent and/or a ring of holes of any superellipse shape.

Kept separate from geometry.py so the simulator version hash (provenance.SIM_FILES) and every cached
slit-only result stay valid; holed designs carry this file's source hash in their cache/design keys instead.

CutDesign = Design + cut = (vent_frac, hole_frac, n_holes, hole_r, hole_aspect, hole_p, hole_rot_deg):
- central circular vent of area vent_frac * A0;
- n_holes holes of total area hole_frac * A0, centred at radius hole_r * R_eq, between the lines
  (azimuths slit_angle_offset + 360k/n, i.e. where the slits sit);
- hole shape: superellipse |x/a|^p + |y/b|^p = 1 with radial/tangential axis ratio hole_aspect
  (> 1 radial slot, < 1 tangential slot), exponent hole_p (2 = ellipse/circle, large = rounded rectangle,
  1 = diamond, < 1 = 4-point star), rotated by hole_rot_deg from the radial direction.
Material is removed, so the outline grows until the net area is A0 again (same rule as slots).
Radial slits (Design.slit_len/slit_r) can be combined with cut-outs.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .geometry import (Design, Geometry, boundary_radius, canonicalize, check_feasible, geometry_features,
                       outline_from_radial, polygon_area, polygon_perimeter, superellipse_unit)

CUT_NAMES = ("vent_frac", "hole_frac", "n_holes", "hole_r", "hole_aspect", "hole_p", "hole_rot_deg")


@dataclass
class CutDesign(Design):
    cut: tuple | None = None

    def as_tuple(self):
        return super().as_tuple() + tuple(float(v) for v in (self.cut or (0, 0, 0, 0, 1, 2, 0)))

    def key_extra(self) -> dict:
        c = canonical_cut(self.cut)
        return {"cut": list(c), "cutouts_src": source_hash()} if c else {}


def source_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


def canonical_cut(cut) -> tuple | None:
    """No open area -> None; without ring holes the ring parameters are fixed; a circle has no rotation."""
    if cut is None:
        return None
    c = list(cut) + [2.0, 0.0][max(0, len(cut) - 5):]
    vent, hole, n, r, asp, pexp, rot = (float(c[0]), float(c[1]), int(round(c[2])), float(c[3]), float(c[4]),
                                        float(c[5]), float(c[6]))
    if hole <= 0.0 or n <= 0:
        hole, n, r, asp, pexp, rot = 0.0, 0, 0.0, 1.0, 2.0, 0.0
    if abs(asp - 1.0) < 1e-12 and abs(pexp - 2.0) < 1e-12:
        rot = 0.0
    if vent <= 0.0 and hole <= 0.0:
        return None
    return (max(vent, 0.0), hole, n, r, asp, pexp, rot % 180.0)


def hole_polygon(center, area: float, aspect: float, pexp: float, ang: float, n: int) -> np.ndarray:
    """Superellipse hole (CCW polygon) of exact polygon area `area`: axis ratio `aspect` along direction
    `ang` (radians), exponent pexp."""
    unit = superellipse_unit(pexp, n) * np.array([aspect, 1.0])
    u = np.array([math.cos(ang), math.sin(ang)])
    v = np.array([-u[1], u[0]])
    p = unit[:, :1] * u + unit[:, 1:] * v
    p *= math.sqrt(area / polygon_area(p))
    return np.asarray(center) + p


def cutout_polygons(cut, R_eq: float, A0: float, offset_rad: float, n_pts: int = 96) -> list:
    if cut is None:
        return []
    vent, hole, n, r, asp, pexp, rot = cut
    holes = []
    if vent > 0:
        holes.append(hole_polygon((0.0, 0.0), vent * A0, 1.0, 2.0, 0.0, n_pts))
    if hole > 0 and n > 0:
        for k in range(n):
            ang = offset_rad + 2 * math.pi * k / n
            c = r * R_eq * np.array([math.cos(ang), math.sin(ang)])
            holes.append(hole_polygon(c, hole * A0 / n, asp, pexp, ang + math.radians(rot), max(n_pts // 2, 48)))
    return holes


def build_cut_geometry(design: Design, cfg: dict, check: bool = True) -> Geometry:
    """Like geometry.build_geometry, plus cut-outs (Geometry gets a `holes` attribute, list of polygons)."""
    cc = cfg["canopy"]
    A0 = float(cc["A0_m2"])
    R_eq = math.sqrt(A0 / math.pi)
    cut = canonical_cut(getattr(design, "cut", None))
    base = canonicalize(Design(design.q, design.slit_len, design.slit_r, design.radial), cfg)
    d = CutDesign(base.q, base.slit_len, base.slit_r, base.radial, cut)
    off = math.radians(cc["slit_angle_offset_deg"])
    holes = cutout_polygons(cut, R_eq, A0, off)
    n_slits = int(cc["n_slits"])
    l_m, r_m = d.slit_len * R_eq, d.slit_r * R_eq
    area_removed = n_slits * l_m * float(cc["slit_width_m"]) + sum(polygon_area(h) for h in holes)
    if d.radial is not None:
        outline = outline_from_radial(np.asarray(d.radial, float), A0 + area_removed, int(cc["outline_points"]))
        a = float("nan")
    else:
        unit = superellipse_unit(float(d.q), int(cc["outline_points"]))
        a = math.sqrt((A0 + area_removed) / polygon_area(unit))
        outline = unit * a
    angles = off + np.arange(n_slits) * 2 * np.pi / n_slits
    slits = (np.array([[u * (r_m - l_m / 2), u * (r_m + l_m / 2)] for u in
                       (np.array([math.cos(t), math.sin(t)]) for t in angles)]) if l_m > 0 else np.zeros((0, 2, 2)))
    from .payload import line_angles
    attach = np.array([[(boundary_radius(outline, t) - cc["attach_inset_m"]) * math.cos(t),
                        (boundary_radius(outline, t) - cc["attach_inset_m"]) * math.sin(t)] for t in line_angles(cfg)])
    g = Geometry(d, outline, slits, angles if l_m > 0 else np.zeros(0), attach, A0, R_eq, a,
                 polygon_area(outline), area_removed)
    g.holes = holes
    if check:
        ok, reasons = check_feasible(g, cfg)
        if holes:
            reasons = reasons + check_holes(g, cfg)
        g.feasible, g.reasons = (len(reasons) == 0), reasons
    return g


def polygon_hash(g: Geometry) -> str:
    h = hashlib.sha256(g.polygon_hash().encode())
    for hole in getattr(g, "holes", []):
        h.update(np.ascontiguousarray(hole, dtype="<f8").tobytes())
    return h.hexdigest()[:16]


def check_holes(g: Geometry, cfg: dict) -> list:
    """Cut-outs must stay inside the outline with a margin, clear of the line patches, slits and each other."""
    from matplotlib.path import Path as MplPath
    from scipy.spatial.distance import cdist
    cc = cfg["canopy"]
    b = cfg.get("cutouts", {}).get("bounds", {})
    reasons = []
    for name, val in zip(CUT_NAMES, g.design.cut):
        if name in b and val != 0 and not (b[name][0] <= val <= b[name][1]):
            reasons.append(f"{name}_out_of_bounds")
    inner = MplPath(g.outline)
    m, bridge = cc["edge_margin_m"], cc["min_bridge_m"]
    if any(not inner.contains_points(h).all() or cdist(h, g.outline).min() < m for h in g.holes):
        reasons.append("hole_reaches_edge")
    if any(cdist(g.attach_points, h).min() < cc["attach_patch_radius_m"] + bridge for h in g.holes):
        reasons.append("hole_intersects_attachment_patch")
    if any(cdist(g.holes[i], g.holes[j]).min() < bridge
           for i in range(len(g.holes)) for j in range(i + 1, len(g.holes))):
        reasons.append("holes_too_close")
    for s in g.slits:
        pts = s[0] + np.linspace(0, 1, 50)[:, None] * (s[1] - s[0])
        if any(cdist(pts, h).min() < bridge or MplPath(h).contains_points(pts).any() for h in g.holes):
            reasons.append("slit_too_close_to_hole")
            break
    return reasons


def cut_features(g: Geometry) -> dict:
    """Generic features (zero without cut-outs): open area fraction of the outline (geometric porosity), vent
    share of the open area, area-weighted mean radius of the open area, total cut-out edge length, hole shape."""
    holes = getattr(g, "holes", [])
    cut = getattr(g.design, "cut", None)
    if not holes:
        return {"open_frac": 0.0, "vent_share": 0.0, "open_r_norm": 0.0, "open_perimeter_norm": 0.0,
                "hole_aspect": 1.0, "hole_p": 2.0}
    areas = np.array([polygon_area(h) for h in holes])
    radii = np.array([np.linalg.norm(h.mean(axis=0)) for h in holes])
    vent_a = areas[0] if cut[0] > 0 else 0.0
    return {"open_frac": float(areas.sum() / g.area_outline), "vent_share": float(vent_a / areas.sum()),
            "open_r_norm": float((areas * radii).sum() / areas.sum() / g.R_eq),
            "open_perimeter_norm": float(sum(polygon_perimeter(h) for h in holes) / g.R_eq),
            "hole_aspect": float(cut[4]), "hole_p": float(cut[5])}


def all_features(g: Geometry) -> dict:
    return geometry_features(g) | cut_features(g)


def build_any_geometry(design: Design, cfg: dict, check: bool = True) -> Geometry:
    """Dispatch on the design family: free-form field, cut-outs, or the original superellipse + slits."""
    from .freeform import FreeDesign, build_free_geometry
    from .geometry import build_geometry
    if isinstance(design, FreeDesign):
        return build_free_geometry(design, cfg, check)
    if getattr(design, "cut", None):
        return build_cut_geometry(design, cfg, check)
    return build_geometry(design, cfg, check)
