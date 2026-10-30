"""Payload V2 (CAD handoff 2026-10-29: DDD-Base.STL + DDD-Cap.STL) -> simulator assets + config block.

CAD frame: millimetres, Y up, base disc centred at (45, *, 45). Flight orientation: the disc is ON TOP
(lines go up from its 6 rim slots to the canopy) and the electronics box + cap hang BELOW it, so the centre
of mass is below the line attachments (stable pendulum; the CAD orientation, box above the attachments,
flips over in flight). Payload frame: metres, Z up, origin at the lowest point (cap bottom):
X = x - 45, Y = z - 45, Z = 50 - y (a proper rotation). The cap is assumed to close the box (box end at CAD
y = 37, cap centred on the box footprint). Anchors = centres of the 6 rim slots on the disc's upper face.
Run: python/.venv/bin/python scripts/v2/make_payload_v2.py
"""
import json
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[2]
A = ROOT / "assets" / "payload_v2"
base = trimesh.load(A / "base.stl", force="mesh")
cap = trimesh.load(A / "cap.stl", force="mesh")

# cap onto the box: box footprint centre (CAD x, z) and top (CAD y = 37)
V = base.vertices
box = V[(V[:, 1] >= 25) & (V[:, 1] <= 35)]
bx, bz = (box[:, 0].min() + box[:, 0].max()) / 2, (box[:, 2].min() + box[:, 2].max()) / 2
cb = cap.bounds
cap.apply_translation([bx - (cb[0, 0] + cb[1, 0]) / 2, V[:, 1].max() - cb[0, 1], bz - (cb[0, 2] + cb[1, 2]) / 2])

R = np.array([[1, 0, 0, -45.0], [0, 0, 1, -45.0], [0, -1, 0, 50.0], [0, 0, 0, 1]])   # CAD mm -> payload mm (flipped)
for m, name in ((base, "base_frame.stl"), (cap, "cap_frame.stl")):
    m.apply_transform(R)
    m.export(A / name)

# rim slots: XZ coverage test of the base (now XY) triangles over the ring r = 30..44 mm
T = base.triangles[:, :, :2]
g = np.mgrid[-45:45:0.25, -45:45:0.25].reshape(2, -1).T
g = g[(np.hypot(*g.T) > 30) & (np.hypot(*g.T) < 44)]


def covered(P):
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    out = np.zeros(len(P), bool)
    for i in range(0, len(P), 2000):
        p = P[i:i + 2000, None, :]
        v0, v1, v2 = c - a, b - a, p - a
        d00, d01, d11 = (v0 * v0).sum(-1), (v0 * v1).sum(-1), (v1 * v1).sum(-1)
        d20, d21 = (v2 * v0).sum(-1), (v2 * v1).sum(-1)
        den = d00 * d11 - d01 * d01
        with np.errstate(divide="ignore", invalid="ignore"):
            u = (d11 * d20 - d01 * d21) / den
            v = (d00 * d21 - d01 * d20) / den
        out[i:i + 2000] = np.nan_to_num((u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)).any(1)
    return out


miss = g[~covered(g)]
from scipy.cluster.hierarchy import fcluster, linkage
lab = fcluster(linkage(miss, "single"), 0.6, "distance")
slots = [miss[lab == k].mean(0) for k in np.unique(lab) if (lab == k).sum() > 50]
slots = sorted(slots, key=lambda p: np.arctan2(p[1], p[0]) % (2 * np.pi))
disc_top = float(base.vertices[np.hypot(*base.vertices[:, :2].T) > 43, 2].max())
anchors_mm = [[round(float(p[0]), 3), round(float(p[1]), 3), round(disc_top, 3)] for p in slots]
print("anchors (mm):", anchors_mm)

zmax = float(max(base.bounds[1, 2], cap.bounds[1, 2]))
boxV = base.vertices[base.vertices[:, 2] < 44]
bxmin, bxmax = boxV[:, 0].min(), boxV[:, 0].max()
bymin, bymax = boxV[:, 1].min(), boxV[:, 1].max()
cxc, cyc = (bxmin + bxmax) / 2 / 1000, (bymin + bymax) / 2 / 1000
block = {
    "model": "payload_v2",
    "note": "Parachute payload V2 (CAD handoff 2026-10-29): 90 mm disc with 6 line slots, octagonal electronics box + cap (assumed seated on the box). Mass NOT weighed: nominal 0.095 kg, sensitivity 0.085-0.115 kg.",
    "assets_dir": "assets/payload_v2",
    "visual_meshes": [{"file": "base_frame.stl", "rgb": [0.95, 0.45, 0.1]}, {"file": "cap_frame.stl", "rgb": [0.2, 0.45, 0.85]}],
    "mesh_scale": 0.001,
    "mass_kg": 0.095,
    "mass_sweep_kg": [0.085, 0.115],
    "parts": [
        {"name": "enclosure_print", "kind": "meshes", "files": ["base_frame.stl", "cap_frame.stl"], "mass_kg": 0.035},
        {"name": "battery_9v", "kind": "box", "size_m": [0.0485, 0.0265, 0.0175], "center_m": [cxc, cyc, 0.0225], "mass_kg": 0.0455},
        {"name": "esp32s3", "kind": "box", "size_m": [0.021, 0.0175, 0.004], "center_m": [cxc - 0.01, cyc, 0.036], "mass_kg": 0.003},
        {"name": "bno085", "kind": "box", "size_m": [0.018, 0.025, 0.003], "center_m": [cxc + 0.012, cyc, 0.036], "mass_kg": 0.0025},
        {"name": "wiring_regulator", "kind": "box", "size_m": [0.02, 0.03, 0.01], "center_m": [cxc, cyc, 0.038], "mass_kg": 0.009}
    ],
    "extent_min_m": [-0.045, -0.045, 0.0],
    "extent_max_m": [0.045, 0.045, round(zmax / 1000, 4)],
    "anchors_mm": anchors_mm,
    "anchors_note": "Centres of the 6 rim slots (found from base.stl) on the disc upper face (flight orientation: disc on top, box below); ordered by azimuth.",
    "collision": [
        {"type": "cylinder", "center_m": [0.0, 0.0, 0.0475], "radius_m": 0.045, "half_len_m": 0.0025},
        {"type": "box", "center_m": [round(cxc, 4), round(cyc, 4), 0.029], "half_m": [round((bxmax - bxmin) / 2000, 4), round((bymax - bymin) / 2000, 4), 0.016]},
        {"type": "box", "center_m": [round(cxc, 4), round(cyc, 4), 0.0065], "half_m": [0.03725, 0.02975, 0.0065]}
    ],
    "imu_offset_m": [round(cxc + 0.012, 4), round(cyc, 4), 0.036],
}
(A / "config_block.json").write_text(json.dumps(block, indent=1))
print(json.dumps({k: block[k] for k in ("extent_max_m", "anchors_mm", "imu_offset_m")}, indent=0))
