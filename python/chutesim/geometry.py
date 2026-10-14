"""Canopy geometry: superellipse outline + radial slits under a fixed net-area constraint.

Single source of truth for geometry (MATLAB wraps these functions through the bridge).

Design vector (compact encoding): q (shape exponent), slit_len = l/R_eq, slit_r = r/R_eq
with R_eq = sqrt(A0/pi). Net area A_net = A_outline - A_removed is held at A0 exactly:
for zero-width slits A_removed = 0; for slots the outline is enlarged to compensate.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Design:
    q: float
    slit_len: float  # l / R_eq
    slit_r: float    # midpoint radius / R_eq
    radial: tuple | None = None  # optional free-form outline r(theta)/R_eq (rich encoding); q unused then

    def as_tuple(self):
        return (float(self.q), float(self.slit_len), float(self.slit_r))


@dataclass
class Geometry:
    design: Design
    outline: np.ndarray            # (N,2) closed polygon (no repeated last point), metres
    slits: np.ndarray              # (n,2,2) segment endpoints, metres
    slit_angles: np.ndarray        # radians
    attach_points: np.ndarray      # (n_lines,2) line attachment points on canopy
    A0: float
    R_eq: float
    a: float                       # superellipse scale
    area_outline: float
    area_removed: float
    feasible: bool = True
    reasons: list = field(default_factory=list)

    @property
    def area_net(self) -> float:
        return self.area_outline - self.area_removed

    def polygon_hash(self) -> str:
        h = hashlib.sha256()
        h.update(np.ascontiguousarray(self.outline, dtype="<f8").tobytes())
        h.update(np.ascontiguousarray(self.slits, dtype="<f8").tobytes())
        return h.hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "design": dict(q=self.design.q, slit_len=self.design.slit_len, slit_r=self.design.slit_r),
            "A0_m2": self.A0, "R_eq_m": self.R_eq, "a_m": self.a,
            "area_outline_m2": self.area_outline, "area_removed_m2": self.area_removed,
            "area_net_m2": self.area_net,
            "outline_m": self.outline.tolist(), "slits_m": self.slits.tolist(),
            "attach_points_m": self.attach_points.tolist(),
            "feasible": self.feasible, "reasons": list(self.reasons),
            "polygon_hash": self.polygon_hash(),
        }


def polygon_area(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def polygon_perimeter(p: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.roll(p, -1, axis=0) - p, axis=1)))


def superellipse_unit(q: float, n: int) -> np.ndarray:
    """Unit-scale superellipse |x|^q+|y|^q=1 sampled with points concentrated where curvature is high."""
    th = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
    c, s = np.cos(th), np.sin(th)
    e = 2.0 / q
    x = np.sign(c) * np.abs(c) ** e
    y = np.sign(s) * np.abs(s) ** e
    return np.column_stack([x, y])


def boundary_radius(outline: np.ndarray, angle: float) -> float:
    """Distance from origin to the outline along a ray (outline must be star-shaped about origin)."""
    d = np.array([math.cos(angle), math.sin(angle)])
    best = np.inf
    p0 = outline
    p1 = np.roll(outline, -1, axis=0)
    e = p1 - p0
    # solve t*d = p0 + u*e  ->  [d, -e] [t,u]^T = p0
    det = d[0] * (-e[:, 1]) - d[1] * (-e[:, 0])
    ok = np.abs(det) > 1e-15
    t = (p0[:, 0] * (-e[:, 1]) - p0[:, 1] * (-e[:, 0])) / np.where(ok, det, 1.0)
    u = (d[0] * p0[:, 1] - d[1] * p0[:, 0]) / np.where(ok, det, 1.0)
    m = ok & (u >= -1e-12) & (u <= 1 + 1e-12) & (t > 0)
    if np.any(m):
        best = float(np.min(t[m]))
    return best


def canonicalize(design: Design, cfg: dict) -> Design:
    """Zero-length slits are one geometry regardless of nominal slit position."""
    q = 0.0 if design.radial is not None else float(design.q)
    if design.slit_len == 0.0:
        return Design(q, 0.0, float(cfg["canopy"]["zero_slit_canonical_r"]), design.radial)
    return Design(q, float(design.slit_len), float(design.slit_r), design.radial)


def _point_segment_distance(p, a, b) -> float:
    ab = b - a
    L2 = float(ab @ ab)
    if L2 == 0:
        return float(np.linalg.norm(p - a))
    t = np.clip(float((p - a) @ ab) / L2, 0.0, 1.0)
    return float(np.linalg.norm(p - (a + t * ab)))


def build_geometry(design: Design, cfg: dict, check: bool = True) -> Geometry:
    cc = cfg["canopy"]
    A0 = float(cc["A0_m2"])
    R_eq = math.sqrt(A0 / math.pi)
    design = canonicalize(design, cfg)
    q = float(design.q)
    n_slits = int(cc["n_slits"])
    w = float(cc["slit_width_m"])
    l_m = design.slit_len * R_eq
    r_m = design.slit_r * R_eq
    area_removed = n_slits * l_m * w

    if design.radial is not None:
        outline = outline_from_radial(np.asarray(design.radial, float), A0 + area_removed, int(cc["outline_points"]))
        a = float("nan")
    else:
        unit = superellipse_unit(q, int(cc["outline_points"]))
        a = math.sqrt((A0 + area_removed) / polygon_area(unit))  # exact for the polygon
        outline = unit * a
    area_outline = polygon_area(outline)

    off = math.radians(cc["slit_angle_offset_deg"])
    angles = off + np.arange(n_slits) * 2 * np.pi / n_slits
    slits = []
    for ang in angles:
        d = np.array([math.cos(ang), math.sin(ang)])
        slits.append([d * (r_m - l_m / 2), d * (r_m + l_m / 2)])
    slits = np.array(slits) if l_m > 0 else np.zeros((0, 2, 2))

    n_lines = int(cc["n_lines"])
    from .payload import line_angles
    lang = line_angles(cfg)
    attach = []
    for ang in lang:
        rb = boundary_radius(outline, ang)
        attach.append([(rb - cc["attach_inset_m"]) * math.cos(ang), (rb - cc["attach_inset_m"]) * math.sin(ang)])
    attach = np.array(attach)

    g = Geometry(design, outline, slits, angles if l_m > 0 else np.zeros(0), attach, A0, R_eq, a,
                 area_outline, area_removed)
    if check:
        g.feasible, g.reasons = check_feasible(g, cfg)
    return g


def check_feasible(g: Geometry, cfg: dict) -> tuple[bool, list]:
    cc = cfg["canopy"]
    b = cc["bounds"]
    d = g.design
    reasons = []
    if d.radial is None and not (b["q"][0] <= d.q <= b["q"][1]):
        reasons.append("q_out_of_bounds")
    if d.radial is not None:
        rr = np.asarray(d.radial, float)
        rr = rr * math.sqrt(math.pi / polar_area(rr))
        if not (np.all(np.isfinite(rr)) and rr.min() > 0.35 and rr.max() < 2.2 and np.abs(np.diff(np.r_[rr, rr[0]])).max() < 0.25):
            reasons.append("radial_shape_invalid")
    if not (b["slit_len"][0] <= d.slit_len <= b["slit_len"][1]):
        reasons.append("slit_len_out_of_bounds")
    if d.slit_len > 0 and not (b["slit_r"][0] <= d.slit_r <= b["slit_r"][1]):
        reasons.append("slit_r_out_of_bounds")
    if abs(g.area_net - g.A0) > 1e-9:
        reasons.append("net_area_violation")
    if len(g.slits):
        n = len(g.slits)
        r_in = float(np.linalg.norm(g.slits[0, 0]))
        # bridge between adjacent inner slit ends around the centre
        if 2 * r_in * math.sin(math.pi / n) < cc["min_bridge_m"]:
            reasons.append("center_bridge_too_narrow")
        for k, seg in enumerate(g.slits):
            outer = float(np.linalg.norm(seg[1]))
            rb = boundary_radius(g.outline, float(g.slit_angles[k]))
            if outer > rb - cc["edge_margin_m"]:
                reasons.append("slit_reaches_edge")
                break
        clear = cc["attach_patch_radius_m"] + cc["min_bridge_m"]
        for p in g.attach_points:
            if any(_point_segment_distance(p, s[0], s[1]) < clear for s in g.slits):
                reasons.append("slit_intersects_attachment_patch")
                break
    return (len(reasons) == 0, reasons)


def geometry_features(g: Geometry) -> dict:
    """Generic features used by aero maps; defined for any outline + slit set."""
    P = polygon_perimeter(g.outline)
    c_iso = 4 * math.pi * g.area_outline / P**2
    lens = np.linalg.norm(g.slits[:, 1] - g.slits[:, 0], axis=1) if len(g.slits) else np.zeros(0)
    mids = np.linalg.norm(g.slits.mean(axis=1), axis=1) if len(g.slits) else np.zeros(0)
    porosity = float(np.sum(0.15 * lens**2) / g.A0)  # flap-opening proxy (assumed, L2)
    rad = np.linalg.norm(g.outline, axis=1)
    return {
        "c_iso": c_iso,
        "slit_total_len_norm": float(lens.sum() / g.R_eq),
        "slit_mid_r_norm": float(mids.mean() / g.R_eq) if len(mids) else 0.0,
        "porosity_proxy": porosity,
        "max_radius_norm": float(rad.max() / g.R_eq),
        "outline_radius_norm": float(np.sqrt(np.mean(rad**2)) / g.R_eq),
    }


def rich_outline(g: Geometry, n: int = 64) -> np.ndarray:
    """Radial function r(theta)/R_eq at n equally spaced angles (area-normalized encoding)."""
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.array([boundary_radius(g.outline, t) for t in th]) / g.R_eq


def polar_area(r_norm: np.ndarray) -> float:
    """Area of the polar polygon through r(theta) samples (units of R_eq^2)."""
    n = len(r_norm)
    return 0.5 * math.sin(2 * math.pi / n) * float(np.sum(r_norm * np.roll(r_norm, -1)))


def outline_from_radial(r_norm: np.ndarray, A0: float, n_out: int = 720) -> np.ndarray:
    """Polygon from r(theta) samples (periodic linear interp in angle), rescaled to exact area A0."""
    n = len(r_norm)
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    tq = np.linspace(0, 2 * np.pi, n_out, endpoint=False)
    r = np.interp(tq, np.r_[th, 2 * np.pi], np.r_[r_norm, r_norm[0]])
    p = np.column_stack([r * np.cos(tq), r * np.sin(tq)])
    return p * math.sqrt(A0 / polygon_area(p))
