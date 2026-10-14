"""Payload rigid-body model from the CAD handoff (payload V1).

One fixed rigid assembly (body + hinged lid closed + pin): visual meshes in the shared assembly frame
(mm -> m), simple convex collision primitives, and mass properties built from PARTS rather than a
uniform envelope: the printed enclosure mass is spread over the actual mesh volumes, the battery and
electronics are separate solid blocks. The total is then scaled to cfg payload.mass_kg (nominal
0.090 kg, not weighed) so mass sweeps keep the same COM and normalized inertia.
Recompute once the printed, populated payload is weighed and its COM measured.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import numpy as np

from .config import REPO_ROOT, stable_hash


def _box_inertia(m, size):
    a, b, c = size
    return m / 12.0 * np.diag([b * b + c * c, a * a + c * c, a * a + b * b])


def _shift(I_c, m, d):
    d = np.asarray(d, float)
    return I_c + m * (np.dot(d, d) * np.eye(3) - np.outer(d, d))


@functools.lru_cache(maxsize=8)
def _mass_properties(key: str, pc_json: str) -> dict:
    """Parts-model mass properties; cached on disk (keyed by the payload config hash) so worker processes
    do not re-import trimesh and re-load the CAD meshes for every drop."""
    pc = json.loads(pc_json)
    cache = REPO_ROOT / pc["assets_dir"] / f".mass_properties_{key}.json"
    if cache.exists():
        d = json.loads(cache.read_text())
        return {"mass_parts": d["mass_parts"], "com": np.array(d["com"]), "I_com": np.array(d["I_com"]), "parts": d["parts"]}
    out = _compute_mass_properties(pc)
    cache.write_text(json.dumps({"mass_parts": out["mass_parts"], "com": out["com"].tolist(),
                                 "I_com": out["I_com"].tolist(), "parts": out["parts"]}))
    return out


def _compute_mass_properties(pc: dict) -> dict:
    import trimesh
    adir = REPO_ROOT / pc["assets_dir"]
    s = pc["mesh_scale"]
    parts = []
    for p in pc["parts"]:
        if p["kind"] == "meshes":
            meshes = [trimesh.load(adir / f, force="mesh") for f in p["files"]]
            for mm in meshes:
                mm.apply_scale(s)
            vol = sum(mm.volume for mm in meshes)
            for mm, f in zip(meshes, p["files"]):
                mass = p["mass_kg"] * mm.volume / vol
                mm.density = mass / mm.volume
                parts.append({"name": f"{p['name']}:{f}", "mass": mass, "com": np.array(mm.center_mass),
                              "I_com": np.array(mm.moment_inertia)})
        else:
            parts.append({"name": p["name"], "mass": p["mass_kg"], "com": np.array(p["center_m"], float),
                          "I_com": _box_inertia(p["mass_kg"], p["size_m"])})
    M = sum(p["mass"] for p in parts)
    com = sum(p["mass"] * p["com"] for p in parts) / M
    I = sum(_shift(p["I_com"], p["mass"], p["com"] - com) for p in parts)
    return {"mass_parts": M, "com": com, "I_com": I,
            "parts": [{"name": p["name"], "mass": p["mass"], "com": p["com"].tolist()} for p in parts]}


def mass_properties(cfg: dict) -> dict:
    """Total mass = cfg payload.mass_kg; COM and normalized inertia from the parts model."""
    pc = cfg["payload"]
    mp = _mass_properties(stable_hash(pc), json.dumps(pc, sort_keys=True))
    scale = pc["mass_kg"] / mp["mass_parts"]
    return {"mass": pc["mass_kg"], "com": mp["com"], "I_com": mp["I_com"] * scale,
            "parts_mass_sum": mp["mass_parts"], "parts": mp["parts"]}


def anchors_m(cfg: dict) -> np.ndarray:
    """Line anchor points (eyelet hole centres) in the payload frame, ordered by azimuth."""
    a = np.asarray(cfg["payload"]["anchors_mm"], float) / 1000.0
    return a[np.argsort(np.arctan2(a[:, 1], a[:, 0]) % (2 * np.pi))]


def line_angles(cfg: dict) -> np.ndarray:
    """Azimuths of the suspension lines: matched to the payload anchors so lines run radially."""
    cc = cfg["canopy"]
    if cc.get("line_angles") == "from_payload_anchors":
        a = anchors_m(cfg)
        return np.arctan2(a[:, 1], a[:, 0]) % (2 * np.pi)
    off = np.radians(cc.get("line_angle_offset_deg", 22.5))
    return off + np.arange(cc["n_lines"]) * 2 * np.pi / cc["n_lines"]


def frontal_area(rig_or_pc: dict) -> float:
    lo, hi = np.asarray(rig_or_pc["extent_min_m"]), np.asarray(rig_or_pc["extent_max_m"])
    return float((hi[0] - lo[0]) * (hi[1] - lo[1]))


def corners(rig_or_pc: dict) -> np.ndarray:
    lo, hi = np.asarray(rig_or_pc["extent_min_m"]), np.asarray(rig_or_pc["extent_max_m"])
    return np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])


def write_report(cfg: dict, path: str | Path) -> dict:
    mp = mass_properties(cfg)
    ev, evec = np.linalg.eigh(mp["I_com"])
    rep = {"mass_kg": mp["mass"], "parts_mass_sum_kg": mp["parts_mass_sum"], "com_m": mp["com"].tolist(),
           "inertia_about_com_kgm2": mp["I_com"].tolist(), "principal_moments_kgm2": ev.tolist(),
           "anchors_m": anchors_m(cfg).tolist(), "line_angles_deg": np.degrees(line_angles(cfg)).tolist(),
           "imu_offset_m": cfg["payload"]["imu_offset_m"], "parts": mp["parts"],
           "status": "ESTIMATE (CAD + datasheet masses, not weighed)"}
    Path(path).write_text(json.dumps(rep, indent=1))
    return rep
