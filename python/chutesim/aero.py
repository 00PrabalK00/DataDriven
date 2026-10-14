"""Explicit aerodynamic loads applied through xfrc_applied (MuJoCo fluid model disabled).

Canopy: effective drag area K(t) = K_i + (K_o - K_i)(1 - exp(-t/tau)) acting at the canopy aero
centre, an alignment torque turning the canopy normal into the relative wind, rotational damping and
a stochastic lateral (Ornstein-Uhlenbeck) force standing in for oscillation. Box: bluff-body drag.
All coefficients come from the aero map (L2 placeholder unless calibrated).
"""
from __future__ import annotations

import math

import mujoco
import numpy as np


class AeroModel:
    def __init__(self, model, params: dict, cfg: dict, scenario: dict, rho: float):
        self.m = model
        self.p = params
        self.rho = rho
        self.cid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "canopy")
        self.pid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "payload")
        from .payload import frontal_area
        self.K_box = cfg["payload"]["Cd_box"] * frontal_area(cfg["payload"])
        self.box_rot_damp = cfg["payload"]["rot_damping"]
        self.R_eq = math.sqrt(cfg["canopy"]["A0_m2"] / math.pi)
        self.wind = np.array([scenario["wind"][0], scenario["wind"][1], 0.0])
        K_o = params["K_open_m2"] * (1 + scenario["area_err"])
        K_i = scenario["k_initial_frac"] * K_o
        self.deployed = scenario["deploy_u"] >= params["p_deploy_fail"]
        if not self.deployed:
            K_o = max(K_i, params["K_fail_frac"] * K_o)
        self.K_i, self.K_o, self.tau = K_i, K_o, params["tau_s"]
        self.rng = np.random.default_rng(scenario["osc_seed"])
        self.ou = np.zeros(2)
        self._v6 = np.zeros(6)

    def K(self, t_rel: float) -> float:
        if t_rel <= 0:
            return self.K_i
        return self.K_i + (self.K_o - self.K_i) * (1 - math.exp(-t_rel / self.tau))

    def _vel(self, d, bid):
        mujoco.mj_objectVelocity(self.m, d, mujoco.mjtObj.mjOBJ_BODY, bid, self._v6, 0)
        return self._v6[3:].copy(), self._v6[:3].copy()

    def apply(self, d, t_rel: float, dt: float):
        """Hot path (called every physics step): scalar math to keep Python overhead low."""
        xf = d.xfrc_applied
        rho = self.rho
        wx, wy = self.wind[0], self.wind[1]
        # canopy
        v6 = self._v6
        mujoco.mj_objectVelocity(self.m, d, mujoco.mjtObj.mjOBJ_BODY, self.cid, v6, 0)
        vx, vy, vz = v6[3] - wx, v6[4] - wy, v6[5]
        sp = math.sqrt(vx * vx + vy * vy + vz * vz)
        K = self.K(t_rel)
        qd = 0.5 * rho * sp * sp
        c = -0.5 * rho * K * sp
        th = self.p["osc_tau_s"]
        a = math.sqrt(2 * dt / th)
        n0, n1 = self.rng.standard_normal(2)
        self.ou[0] += -self.ou[0] * dt / th + a * n0
        self.ou[1] += -self.ou[1] * dt / th + a * n1
        lat = self.p["osc_intensity"] * 0.3 * qd * K
        xf[self.cid, 0] = c * vx + lat * self.ou[0]
        xf[self.cid, 1] = c * vy + lat * self.ou[1]
        xf[self.cid, 2] = c * vz
        cr = self.p["rot_damping"]
        tx, ty, tz = -cr * v6[0], -cr * v6[1], -cr * v6[2]
        if sp > 1e-6:
            xm = d.xmat[self.cid]
            nx, ny, nz = xm[2], xm[5], xm[8]  # canopy body z axis in world
            ux, uy, uz = -vx / sp, -vy / sp, -vz / sp
            k = self.p["align_gain"] * qd * K * self.R_eq
            tx += k * (ny * uz - nz * uy)
            ty += k * (nz * ux - nx * uz)
            tz += k * (nx * uy - ny * ux)
        xf[self.cid, 3] = tx
        xf[self.cid, 4] = ty
        xf[self.cid, 5] = tz
        # payload
        mujoco.mj_objectVelocity(self.m, d, mujoco.mjtObj.mjOBJ_BODY, self.pid, v6, 0)
        bx, by, bz = v6[3] - wx, v6[4] - wy, v6[5]
        cb = -0.5 * rho * self.K_box * math.sqrt(bx * bx + by * by + bz * bz)
        xf[self.pid, 0] = cb * bx
        xf[self.pid, 1] = cb * by
        xf[self.pid, 2] = cb * bz
        rd = self.box_rot_damp
        xf[self.pid, 3] = -rd * v6[0]
        xf[self.pid, 4] = -rd * v6[1]
        xf[self.pid, 5] = -rd * v6[2]
        return K
