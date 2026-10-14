"""Sensor-derived metrics with explicit status. A failed measurement is reported as missing (None)
with a status and reason; it is NEVER replaced by 0 or a default value.

Status codes: ok | invalid_tracking | invalid_contact | invalid_sync | invalid_release | clipped
"""
from __future__ import annotations

import numpy as np

from .decel import label_from_series


def M(value=None, status="ok", reason=None, **extra):
    d = {"value": value, "status": status}
    if reason:
        d["reason"] = reason
    d.update(extra)
    return d


def invalid(status, reason):
    return M(None, status, reason)


def detect_release(t, f_s, cp, g) -> float | None:
    """First time |f| stays below release_fmag_g*g for release_hold_s (free fall begins)."""
    mag = np.linalg.norm(f_s, axis=1)
    low = mag < cp["release_fmag_g"] * g
    hold = cp["release_hold_s"]
    for i in np.nonzero(low)[0]:
        j = np.searchsorted(t, t[i] + hold)
        if j < len(t) and np.all(low[i:j + 1]):
            # back off to the last sample above 0.9 g (the hand opening)
            k = i
            while k > 0 and mag[k - 1] < 0.9 * g:
                k -= 1
            return float(t[k])
    return None


def detect_impact_imu(t, f_s, t_release, cp, g, rng_lim) -> float | None:
    mag = np.linalg.norm(f_s, axis=1)
    idx = np.nonzero((t > t_release + 0.1) & (mag > cp["impact_fmag_g"] * g))[0]
    if len(idx) == 0:
        return None
    i = idx[0]
    # onset: walk back to where |f| first left the in-flight band (< 1.5 g)
    while i > 0 and mag[i - 1] > 1.5 * g and t[i - 1] > t_release:
        i -= 1
    return float(t[i])


def payload_corners(rig):
    """Corners of the payload bounding box in the payload frame (from the rig extents)."""
    lo, hi = np.asarray(rig["extent_min_m"]), np.asarray(rig["extent_max_m"])
    return np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])


def z_bottom(rig):
    """Height of the payload frame origin above its lowest point when upright."""
    return -float(rig["extent_min_m"][2])


def lowest_point_z(p, R, corners):
    """World z of the lowest payload corner."""
    zs = p[:, None, 2] + np.einsum("nij,kj->nki", R, corners)[:, :, 2]
    return zs.min(axis=1)


def detect_contact_traj(t, p, R, rig, tol) -> float | None:
    if R is None or len(R) != len(t):
        zlow = p[:, 2] - z_bottom(rig)
    else:
        zlow = lowest_point_z(p, R, payload_corners(rig))
    idx = np.nonzero(zlow <= rig["pad_top_z_m"] + tol)[0]
    if len(idx) == 0:
        return None
    return float(t[idx[0]])


def camera_contact_bracket(meas, rig, tol):
    """From raw camera position measurements: (last airborne time, first on-pad time, h_low)."""
    corners = payload_corners(rig)
    last_air, h_low = None, z_bottom(rig)
    for m in meas:
        if m["type"] not in ("pnp", "fallback"):
            continue
        if m["type"] == "pnp":
            hl = -float(np.min((m["R"] @ corners.T)[2]))
        else:
            hl = z_bottom(rig)
        zlow = m["p"][2] - hl
        if zlow <= rig["pad_top_z_m"] + tol:
            if last_air is None:
                return None
            return last_air, m["t"], h_low
        last_air, h_low = m["t"], hl
    return None


def extrapolate_contact(traj, rig, h_low, t_lo, t_hi):
    """Time the smoothed pre-contact trajectory (const. acceleration from its last state) reaches the pad."""
    p, v, a, t0 = traj["p"][-1, 2], traj["v"][-1, 2], traj["a"][-1, 2], traj["t"][-1]
    target = rig["pad_top_z_m"] + h_low
    A, B, Cc = 0.5 * a, v, p - target
    if abs(A) < 1e-9:
        roots = [-Cc / B] if B != 0 else []
    else:
        disc = B * B - 4 * A * Cc
        roots = [] if disc < 0 else [(-B - np.sqrt(disc)) / (2 * A), (-B + np.sqrt(disc)) / (2 * A)]
    roots = [r for r in roots if r >= 0]
    tc = t0 + min(roots) if roots else t_hi
    return float(min(max(tc, t_lo), t_hi))


def traj_contact_time(t, p, v, R, rig, tol):
    """Pad-crossing time of a trajectory that ends at (or before) contact: first crossing if any,
    otherwise extrapolated from the final state with constant velocity."""
    tc = detect_contact_traj(t, p, R, rig, tol)
    if tc is not None:
        return tc
    zl = lowest_point_z(p[-1:], R[-1:], payload_corners(rig))[0] if R is not None and len(R) else p[-1, 2] - z_bottom(rig)
    vz = v[-1, 2]
    if vz >= -1e-6:
        return None
    return float(t[-1] + (zl - (rig["pad_top_z_m"] + tol)) / -vz)


def preimpact_fit(t, p, tc, cp, min_samples):
    W, guard = cp["preimpact_window_s"], cp["preimpact_guard_s"]
    sel = (t >= tc - W) & (t <= tc - guard)
    if sel.sum() < min_samples:
        return None
    tt = t[sel] - (tc - guard)
    out = {}
    for ax, name in ((2, "vz"), (0, "vx"), (1, "vy")):
        c = np.polyfit(tt, p[sel, ax], 2)
        out[name] = float(c[1])  # derivative at tc - guard
    out["n"] = int(sel.sum())
    return out


def compute_metrics(mode: str, traj: dict, events: dict, imu: dict | None, rig: dict, cp: dict,
                    n_cam_window: int | None = None) -> dict:
    g = rig["g"]
    res = {"mode": mode}
    tc = events.get("contact_t")
    tr = events.get("release_t")
    if events.get("status") != "ok":
        st = events.get("status", "invalid_contact")
        for k in ("preimpact_vz", "lateral_speed", "landing_offset", "tilt_rms_deg", "tilt_max_deg",
                  "swing_rate_rms", "peak_specific_force_g", "decel"):
            res[k] = invalid(st, events.get("reason"))
        res["contact_t"] = None
        return res
    res["contact_t"] = tc
    res["release_t"] = tr
    t, p = traj["t"], traj["p"]
    min_s = cp["preimpact_min_samples"]
    if mode == "fused" and n_cam_window is not None and n_cam_window < min_s:
        fit = None
        why = f"camera measurements near impact={n_cam_window} (<{min_s})"
    else:
        fit = preimpact_fit(t, p, tc, cp, min_s)
        why = "too few trajectory samples in pre-impact window"
    if fit is None:
        res["preimpact_vz"] = invalid("invalid_tracking", why)
        res["lateral_speed"] = invalid("invalid_tracking", why)
    else:
        res["preimpact_vz"] = M(-fit["vz"], n=fit["n"])  # downward positive
        res["lateral_speed"] = M(float(np.hypot(fit["vx"], fit["vy"])))
    # landing offset relative to the nominal release point
    k = int(np.searchsorted(t, tc))
    if 0 < k <= len(t):
        off = p[k - 1, :2] - np.asarray(rig["release_nominal_m"][:2])
        res["landing_offset"] = M(float(np.linalg.norm(off)))
    else:
        res["landing_offset"] = invalid("invalid_tracking", "no trajectory at contact")
    # tilt
    if mode == "camera":
        Rt, Rs = traj.get("R_t", np.zeros(0)), traj.get("R", np.zeros((0, 3, 3)))
        sel = (Rt < tc - cp["preimpact_guard_s"]) & (Rt > tc - 1.0)
        Rw = Rs[sel] if len(Rt) else Rs
    else:
        sel = (t > (tr if tr is not None else -np.inf) + 0.2) & (t < tc - cp["preimpact_guard_s"])
        Rw = traj["R"][sel]
    if len(Rw) >= 3:
        tilt = np.degrees(np.arccos(np.clip(Rw[:, 2, 2], -1, 1)))
        res["tilt_rms_deg"] = M(float(np.sqrt(np.mean(tilt**2))))
        res["tilt_max_deg"] = M(float(np.max(tilt)))
    else:
        res["tilt_rms_deg"] = invalid("invalid_tracking", "no orientation in descent window")
        res["tilt_max_deg"] = invalid("invalid_tracking", "no orientation in descent window")
    # IMU-based metrics
    if imu is not None and tr is not None:
        ti, f_s, w_s = imu["t"], imu["f"], imu["w"]
        sel = (ti > tr + 0.2) & (ti < tc - cp["preimpact_guard_s"])
        if sel.sum() > 5:
            bg = traj.get("bg", np.zeros(3))
            res["swing_rate_rms"] = M(float(np.sqrt(np.mean(np.sum((w_s[sel] - bg) ** 2, axis=1)))))
        else:
            res["swing_rate_rms"] = invalid("invalid_tracking", "no IMU samples in descent window")
        win = (ti >= tc - 0.05) & (ti <= tc + 0.3)
        if win.any():
            peak = float(np.max(np.linalg.norm(f_s[win], axis=1)) / g)
            clipped = bool(np.any(np.abs(f_s[win]) >= imu["range"] - 1e-6))
            res["peak_specific_force_g"] = M(peak, "clipped" if clipped else "ok",
                                             "accelerometer saturated: value is a lower bound" if clipped else None)
        else:
            res["peak_specific_force_g"] = invalid("invalid_tracking", "no IMU samples at impact")
    else:
        res["swing_rate_rms"] = invalid("invalid_tracking", "IMU not used in this mode")
        res["peak_specific_force_g"] = invalid("invalid_tracking", "IMU not used in this mode")
    # deceleration label
    if mode == "camera":
        sel = (t < tc - 0.05) & (t > tc - 0.6)
        f_up = traj["a"][sel, 2] + g if len(t) else np.zeros(0)
        sp = np.linalg.norm(traj["v"][sel], axis=1) if len(t) else np.zeros(0)
        res["decel"] = label_from_series(f_up, sp, rig, cp["decel_factor_vs_box"])
    else:
        ti, f_s = imu["t"], imu["f"]
        sel_i = (ti > tr + cp["decel_window_from_release_s"]) & (ti < tc - 0.05)
        idx = np.searchsorted(t, ti[sel_i]).clip(0, len(t) - 1)
        R = traj["R"][idx]
        R_bs = imu["R_bs"]
        f_w = np.einsum("nij,nj->ni", R, (R_bs @ (f_s[sel_i] - 0).T).T - traj.get("ba", np.zeros(3)))
        sp = np.linalg.norm(traj["v"][idx], axis=1)
        res["decel"] = label_from_series(f_w[:, 2], sp, rig, cp["decel_factor_vs_box"])
    return res
