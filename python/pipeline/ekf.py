"""State estimation.

ESEKF (fused / IMU-only): nominal state p (IMU point, world), v, R (box->world), b_a, b_g (box frame);
15-dim error state. IMU propagation; corrections from camera position (box centre, lever arm to the
IMU), orientation (PnP), and depth axial range; zero-velocity pseudo-measurements while the protocol
says the box is held still (before the detected release).

Camera-only: constant-acceleration Kalman filter + RTS smoother on camera measurements.
"""
from __future__ import annotations

import math

import numpy as np

from .geometry3d import exp_so3, log_so3, orthonormalize, rpy_to_R, skew, yaw_of, Rz

I3 = np.eye(3)


class ESEKF:
    def __init__(self, ec: dict, g: float, r_imu_box: np.ndarray, R_bs: np.ndarray):
        self.ec = ec
        self.gw = np.array([0, 0, -g])
        self.r = np.asarray(r_imu_box, float)   # IMU position in box frame (box centre = origin)
        self.c = -self.r                         # box centre relative to IMU point, box frame
        self.R_bs = R_bs
        self.p = np.zeros(3)
        self.v = np.zeros(3)
        self.R = np.eye(3)
        self.ba = np.zeros(3)
        self.bg = np.zeros(3)
        self.P = np.eye(15)
        self.f_last = np.array([0, 0, g])
        self.w_last = np.zeros(3)

    def init(self, p, R, bg, sd_p, sd_v, sd_rp, sd_yaw, sd_ba, sd_bg):
        self.p, self.R, self.bg = np.asarray(p, float), R, np.asarray(bg, float)
        self.v = np.zeros(3)
        self.ba = np.zeros(3)
        self.P = np.diag(np.r_[[sd_p**2] * 3, [sd_v**2] * 3, [sd_rp**2, sd_rp**2, sd_yaw**2], [sd_ba**2] * 3, [sd_bg**2] * 3])

    def set_imu(self, f_s, w_s):
        self.f_last = self.R_bs @ f_s
        self.w_last = self.R_bs @ w_s

    def propagate(self, dt):
        if dt <= 0:
            return np.eye(15)
        ec = self.ec
        f = self.f_last - self.ba
        w = self.w_last - self.bg
        a = self.R @ f + self.gw
        self.p = self.p + self.v * dt + 0.5 * a * dt * dt
        self.v = self.v + a * dt
        self.R = orthonormalize(self.R @ exp_so3(w * dt))
        F = np.eye(15)
        F[0:3, 3:6] = I3 * dt
        F[3:6, 6:9] = -self.R @ skew(f) * dt
        F[3:6, 9:12] = -self.R * dt
        F[6:9, 6:9] = exp_so3(-w * dt)
        F[6:9, 12:15] = -I3 * dt
        Q = np.zeros((15, 15))
        Q[3:6, 3:6] = I3 * ec["accel_noise"] ** 2 * dt
        Q[6:9, 6:9] = I3 * ec["gyro_noise"] ** 2 * dt
        Q[9:12, 9:12] = I3 * ec["accel_bias_rw"] ** 2 * dt
        Q[12:15, 12:15] = I3 * ec["gyro_bias_rw"] ** 2 * dt
        self.P = F @ self.P @ F.T + Q
        return F

    def state(self):
        return (self.p.copy(), self.v.copy(), self.R.copy(), self.ba.copy(), self.bg.copy())

    def _update(self, r, H, Rm):
        S = H @ self.P @ H.T + Rm
        K = self.P @ H.T @ np.linalg.inv(S)
        dx = K @ r
        IKH = np.eye(15) - K @ H
        self.P = IKH @ self.P @ IKH.T + K @ Rm @ K.T
        self.p += dx[0:3]
        self.v += dx[3:6]
        self.R = orthonormalize(self.R @ exp_so3(dx[6:9]))
        self.ba += dx[9:12]
        self.bg += dx[12:15]
        return float(r @ np.linalg.solve(S, r))

    def center(self):
        return self.p + self.R @ self.c

    def center_velocity(self):
        w = self.w_last - self.bg
        return self.v + self.R @ np.cross(w, self.c)

    def update_position(self, p_center, cov):
        H = np.zeros((3, 15))
        H[:, 0:3] = I3
        H[:, 6:9] = -self.R @ skew(self.c)
        return self._update(p_center - self.center(), H, cov)

    def update_anchor(self, p_anchor, anchor_box, cov):
        """Camera-observed point fixed to the box (marker-face anchor); lever arm via filter attitude."""
        lever = self.c + np.asarray(anchor_box)
        H = np.zeros((3, 15))
        H[:, 0:3] = I3
        H[:, 6:9] = -self.R @ skew(lever)
        return self._update(p_anchor - (self.p + self.R @ lever), H, cov)

    def update_attitude(self, R_meas, sd):
        H = np.zeros((3, 15))
        H[:, 6:9] = I3
        return self._update(log_so3(self.R.T @ R_meas), H, I3 * sd**2)

    def update_depth(self, z_cam, sd, R_wc, t_wc):
        e = R_wc[:, 2]  # optical axis in world
        h = float(e @ (self.center() - t_wc))
        H = np.zeros((1, 15))
        H[0, 0:3] = e
        H[0, 6:9] = e @ (-self.R @ skew(self.c))
        return self._update(np.array([z_cam - h]), H, np.array([[sd**2]]))

    def zupt(self, sd=0.01):
        H = np.zeros((3, 15))
        H[:, 3:6] = I3
        return self._update(-self.v, H, I3 * sd**2)


def initial_attitude(f_body_mean: np.ndarray, yaw: float) -> np.ndarray:
    """R (box->world) whose world-z is along the measured specific force, with the given yaw."""
    zb = f_body_mean / np.linalg.norm(f_body_mean)  # world z expressed in box frame
    roll = math.atan2(zb[1], zb[2])
    pitch = math.atan2(-zb[0], math.hypot(zb[1], zb[2]))
    return rpy_to_R(roll, pitch, yaw)


def _boxminus(xa, xb):
    """Error-state difference xa (-) xb (local attitude error)."""
    return np.r_[xa[0] - xb[0], xa[1] - xb[1], log_so3(xb[2].T @ xa[2]), xa[3] - xb[3], xa[4] - xb[4]]


def _boxplus(x, d):
    return (x[0] + d[0:3], x[1] + d[3:6], orthonormalize(x[2] @ exp_so3(d[6:9])), x[3] + d[9:12], x[4] + d[12:15])


def run_esekf(imu_t, f_s, w_s, meas, rig: dict, ec: dict, t_release: float, use_camera: bool,
              calib: dict, yaw0: float = 0.0, yaw_sd: float | None = None, smooth: bool = True) -> dict:
    """Forward ESEKF on the IMU time grid + error-state RTS smoother.

    Camera measurements are applied at the next IMU time; their position/range is motion-compensated
    by v_est * (t_imu - t_meas) (at most one IMU period), which keeps the filter on one time grid so
    the smoother is exact for the discretised model."""
    from .geometry3d import rpy_to_R as _rpy
    R_bs = _rpy(*np.radians(rig["imu_mount_rpy_deg"]))
    f_b = (R_bs @ f_s.T).T
    w_b = (R_bs @ w_s.T).T
    still = imu_t < t_release - 0.1
    if still.sum() < 10:
        still = imu_t < imu_t[0] + 0.2
    R0 = initial_attitude(f_b[still].mean(0), yaw0)
    bg0 = w_b[still].mean(0)
    r_imu = np.asarray(rig["imu_offset_m"], float)
    p0 = np.asarray(rig["release_nominal_m"], float) + R0 @ r_imu
    kf = ESEKF(ec, rig["g"], r_imu, R_bs)
    if yaw_sd is None:
        yaw_sd = math.pi if use_camera else 0.02
    kf.init(p0, R0, bg0, ec["init_pos_sd_m"], 0.05, 0.02, yaw_sd, 0.15, 0.005)
    R_wc = np.asarray(calib["T_world_color"]["R"])
    t_wc = np.asarray(calib["T_world_color"]["t"])

    n = len(imu_t)
    xs_post, Ps_post, xs_pred, Ps_pred, Fs = [], [], [], [], []
    m_list = meas if use_camera else []
    mi = 0
    first_att = None
    nis = []
    for k in range(n):
        tk = imu_t[k]
        kf.set_imu(f_s[k], w_s[k])
        F = kf.propagate(tk - imu_t[k - 1]) if k > 0 else np.eye(15)
        Fs.append(F)
        xs_pred.append(kf.state())
        Ps_pred.append(kf.P.copy())
        while mi < len(m_list) and m_list[mi]["t"] <= tk:
            m = m_list[mi]
            lag = tk - m["t"]
            vc = kf.center_velocity()
            if m["type"] == "fallback":
                nis.append(kf.update_position(m["p"] + vc * lag, m["cov"]))
            if m["type"] == "pnp":
                nis.append(kf.update_anchor(m["anchor_w"] + vc * lag, m["anchor_box"], m["cov"]))
                if first_att is None:
                    first_att = (yaw_of(m["R"]) - yaw_of(kf.R), m["t"])
                kf.update_attitude(m["R"], m["att_sd"])
            if m["type"] == "depth":
                kf.update_depth(m["z_cam"] + float(R_wc[:, 2] @ vc) * lag, m["sd"], R_wc, t_wc)
            mi += 1
        if tk < t_release - 0.05:
            kf.zupt()
        xs_post.append(kf.state())
        Ps_post.append(kf.P.copy())

    xs = list(xs_post)
    Psd = [np.sqrt(np.diag(P)) for P in Ps_post]
    if smooth and n > 1:
        Ps = Ps_post[-1]
        for k in range(n - 2, -1, -1):
            C = Ps_post[k] @ Fs[k + 1].T @ np.linalg.inv(Ps_pred[k + 1])
            d = C @ _boxminus(xs[k + 1], xs_pred[k + 1])
            xs[k] = _boxplus(xs_post[k], d)
            Ps = Ps_post[k] + C @ (Ps - Ps_pred[k + 1]) @ C.T
            Psd[k] = np.sqrt(np.clip(np.diag(Ps), 0, None))
    c = -r_imu
    out_p = np.array([x[0] + x[2] @ c for x in xs])
    out_R = np.array([x[2] for x in xs])
    wb = w_b - np.array([x[4] for x in xs])
    out_v = np.array([x[1] + x[2] @ np.cross(wb[k], c) for k, x in enumerate(xs)])
    return {"t": imu_t, "p": out_p, "v": out_v, "R": out_R, "p_sd": np.array(Psd)[:, 0:3],
            "first_att": first_att, "ba": xs[-1][3], "bg": xs[-1][4],
            "nis_mean": float(np.mean(nis)) if nis else None}


def fused(imu_t, f_s, w_s, meas, rig, ec, t_release, calib) -> dict:
    """Two-pass: pass 1 finds the yaw offset at the first camera orientation fix; pass 2 restarts
    with the corrected initial yaw (avoids linearising a large yaw error)."""
    r1 = run_esekf(imu_t, f_s, w_s, meas, rig, ec, t_release, True, calib, 0.0)
    if r1["first_att"] is None:
        return r1
    dyaw = r1["first_att"][0]
    return run_esekf(imu_t, f_s, w_s, meas, rig, ec, t_release, True, calib, dyaw, yaw_sd=0.2)


def imu_only(imu_t, f_s, w_s, rig, ec, t_release, calib) -> dict:
    return run_esekf(imu_t, f_s, w_s, [], rig, ec, t_release, False, calib, 0.0)


def camera_only(meas, calib, psd: float, t_cut: float | None = None) -> dict:
    """Constant-acceleration KF + RTS smoother over camera measurements (position + depth axial).
    t_cut: only measurements strictly before this time are used (pre-contact segment), so the
    smoother never rounds off the impact."""
    ms = [m for m in meas if m["type"] in ("pnp", "fallback", "depth") and (t_cut is None or m["t"] < t_cut)]
    if len(ms) < 2:
        return {"t": np.zeros(0), "p": np.zeros((0, 3)), "v": np.zeros((0, 3)), "a": np.zeros((0, 3)),
                "R_t": np.zeros(0), "R": np.zeros((0, 3, 3)), "n_meas": len(ms)}
    R_wc = np.asarray(calib["T_world_color"]["R"])
    t_wc = np.asarray(calib["T_world_color"]["t"])
    first = next((m for m in ms if m["type"] != "depth"), None)
    if first is None:
        return {"t": np.zeros(0), "p": np.zeros((0, 3)), "v": np.zeros((0, 3)), "a": np.zeros((0, 3)),
                "R_t": np.zeros(0), "R": np.zeros((0, 3, 3)), "n_meas": len(ms)}
    x = np.zeros(9)
    x[0:3] = first["p"]
    x[6:9] = [0, 0, -9.81]
    P = np.diag([0.05**2] * 3 + [5.0**2] * 3 + [10.0**2] * 3)
    xs, Ps, xps, Pps, Fs, ts = [], [], [], [], [], []
    t_prev = first["t"]
    for m in ms:
        if m["t"] < first["t"]:
            continue
        dt = m["t"] - t_prev
        F = np.eye(9)
        F[0:3, 3:6] = I3 * dt
        F[0:3, 6:9] = I3 * dt * dt / 2
        F[3:6, 6:9] = I3 * dt
        G = np.r_[I3 * dt**3 / 6, I3 * dt**2 / 2, I3 * dt]
        Q = G @ G.T * psd / max(dt, 1e-3)
        xp = F @ x
        Pp = F @ P @ F.T + Q
        if m["type"] == "depth":
            H = np.zeros((1, 9))
            H[0, 0:3] = R_wc[:, 2]
            r = np.array([m["z_cam"] - R_wc[:, 2] @ (xp[0:3] - t_wc)])
            Rm = np.array([[m["sd"] ** 2]])
        else:
            H = np.zeros((3, 9))
            H[:, 0:3] = I3
            r = m["p"] - xp[0:3]
            Rm = m["cov"]
        S = H @ Pp @ H.T + Rm
        K = Pp @ H.T @ np.linalg.inv(S)
        x = xp + K @ r
        P = (np.eye(9) - K @ H) @ Pp
        xs.append(x); Ps.append(P); xps.append(xp); Pps.append(Pp); Fs.append(F); ts.append(m["t"])
        t_prev = m["t"]
    # RTS smoother
    n = len(xs)
    xsm, Psm = list(xs), list(Ps)
    for k in range(n - 2, -1, -1):
        C = Ps[k] @ Fs[k + 1].T @ np.linalg.inv(Pps[k + 1])
        xsm[k] = xs[k] + C @ (xsm[k + 1] - xps[k + 1])
        Psm[k] = Ps[k] + C @ (Psm[k + 1] - Pps[k + 1]) @ C.T
    X = np.array(xsm)
    att = [(m["t"], m["R"]) for m in ms if m["type"] == "pnp"]
    return {"t": np.array(ts), "p": X[:, 0:3], "v": X[:, 3:6], "a": X[:, 6:9],
            "p_sd": np.sqrt(np.array([np.diag(P)[0:3] for P in Psm])),
            "R_t": np.array([a[0] for a in att]), "R": np.array([a[1] for a in att]).reshape(-1, 3, 3),
            "n_meas": len(ms)}
