"""Small rotation / camera-geometry helpers shared by the pipeline."""
from __future__ import annotations

import math

import numpy as np


def skew(v):
    return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])


def exp_so3(w):
    th = float(np.linalg.norm(w))
    if th < 1e-10:
        return np.eye(3) + skew(w)
    k = w / th
    K = skew(k)
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K


def log_so3(R):
    c = (np.trace(R) - 1) / 2
    c = min(1.0, max(-1.0, c))
    th = math.acos(c)
    if th < 1e-8:
        return np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / 2
    return th / (2 * math.sin(th)) * np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])


def rpy_to_R(r, p, y):
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def yaw_of(R):
    return math.atan2(R[1, 0], R[0, 0])


def Rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def orthonormalize(R):
    u, _, vt = np.linalg.svd(R)
    return u @ vt


def K_matrix(intr: dict) -> np.ndarray:
    return np.array([[intr["fx"], 0, intr["cx"]], [0, intr["fy"], intr["cy"]], [0, 0, 1.0]])


def align_depth_to_color(depth_u16: np.ndarray, calib: dict, roi=None) -> np.ndarray:
    """Map raw depth (depth imager) into the colour image grid with a z-buffer (nearest wins).
    Pixels with no projected depth stay 0: this is where alignment gaps and occlusion holes appear.
    roi = (x0, y0, x1, y1) in colour pixels limits the work (output is still full size)."""
    di, ci = calib["depth"], calib["color"]
    R = np.asarray(calib["T_color_depth"]["R"], np.float32)
    t = np.asarray(calib["T_color_depth"]["t"], np.float32)[:, None]
    dv0 = du0 = 0
    if roi is not None:
        # only depth pixels that can land in the colour ROI: map the ROI corners back into the depth
        # image at the nearest and farthest valid depths and crop to their bounding box (exact superset)
        x0, y0, x1, y1 = roi
        cs = np.array([[x0, y0], [x1, y0], [x0, y1], [x1, y1]], float)
        pts = []
        for Z in (0.25, 8.0):
            Xc = np.stack([(cs[:, 0] - ci["cx"]) / ci["fx"] * Z, (cs[:, 1] - ci["cy"]) / ci["fy"] * Z, np.full(4, Z)])
            Xd = R.T @ (Xc - t)
            pts.append(np.stack([di["fx"] * Xd[0] / Xd[2] + di["cx"], di["fy"] * Xd[1] / Xd[2] + di["cy"]], 1))
        pts = np.vstack(pts)
        du0 = int(max(np.floor(pts[:, 0].min()) - 3, 0))
        dv0 = int(max(np.floor(pts[:, 1].min()) - 3, 0))
        du1 = int(min(np.ceil(pts[:, 0].max()) + 4, depth_u16.shape[1]))
        dv1 = int(min(np.ceil(pts[:, 1].max()) + 4, depth_u16.shape[0]))
        depth_u16 = depth_u16[dv0:dv1, du0:du1]
    z = depth_u16.astype(np.float32) * np.float32(calib["depth_unit_m"])
    v, u = np.nonzero(z > 0)
    zz = z[v, u]
    v = v + dv0
    u = u + du0
    X = np.stack([(u - di["cx"]) / di["fx"] * zz, (v - di["cy"]) / di["fy"] * zz, zz], axis=0)
    Xc = R @ X + t
    with np.errstate(divide="ignore", invalid="ignore"):
        uc = np.rint(ci["fx"] * Xc[0] / Xc[2] + ci["cx"]).astype(np.int64)
        vc = np.rint(ci["fy"] * Xc[1] / Xc[2] + ci["cy"]).astype(np.int64)
    ok = (Xc[2] > 0) & (uc >= 0) & (uc < ci["width"]) & (vc >= 0) & (vc < ci["height"])
    if roi is not None:
        x0, y0, x1, y1 = roi
        ok &= (uc >= x0) & (uc < x1) & (vc >= y0) & (vc < y1)
    uc, vc, zc = uc[ok], vc[ok], Xc[2][ok]
    order = np.argsort(-zc)  # far first; nearest written last wins
    out = np.zeros((ci["height"], ci["width"]), np.float32)
    out[vc[order], uc[order]] = zc[order]
    return out
