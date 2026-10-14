"""Physics run of one drop: build the scene for (design, scenario), hold, release, integrate.

Returns the full-rate state history. Everything here is simulator truth; only sensors.py and
camera.py turn it into observations.
"""
from __future__ import annotations

import math

import mujoco
import numpy as np

from .aero import AeroModel
from .aeromap import get_map
from .geometry import Design, build_geometry
from .payload import anchors_m
from .scene import _rpy_to_quat, build_mjcf


def fabricated_geometry(design: Design, scenario: dict, cfg: dict):
    """Geometry actually cut (slit-length fabrication error); nominal net area constraint kept."""
    g_nom = build_geometry(design, cfg)
    if design.slit_len > 0:
        dl = scenario["slit_len_err_m"] / g_nom.R_eq
        g_fab = build_geometry(Design(design.q, max(design.slit_len + dl, 1e-6), design.slit_r, design.radial), cfg,
                               check=False)
    else:
        g_fab = g_nom
    return g_nom, g_fab


def end_time(cfg: dict) -> float:
    return float(cfg["drop"]["duration_s"])


def simulate_physics(design: Design, scenario: dict, cfg: dict, timestep: float | None = None,
                     vertical_only: bool = False) -> dict:
    cfg_p = cfg["physics"]
    dt = float(timestep or cfg_p["timestep"])
    g_nom, g_fab = fabricated_geometry(design, scenario, cfg)
    amap, aver = get_map(cfg)
    params = amap(g_fab, cfg)
    rho = cfg_p["rho"] * (1 + scenario["rho_frac"])

    pc, cc, dr = cfg["payload"], cfg["canopy"], cfg["drop"]
    z_bottom = -pc["extent_min_m"][2]          # payload frame origin height above its lowest point
    anchors = anchors_m(cfg)
    L = np.asarray(cc["line_length_m"] + np.asarray(scenario["line_len_err"]))
    if vertical_only:
        roll = pitch = 0.0
        v0 = np.zeros(3)
    else:
        roll, pitch = scenario["roll"], scenario["pitch"]
        v0 = np.asarray(scenario["v0"])
    yaw = scenario["yaw"]
    qp = _rpy_to_quat(roll, pitch, yaw)
    Rm = np.zeros(9)
    mujoco.mju_quat2Mat(Rm, qp)
    Rm = Rm.reshape(3, 3)
    p0 = np.array([dr["release_xy_m"][0] + scenario["dxy"][0], dr["release_xy_m"][1] + scenario["dxy"][1],
                   dr["height_m"] + z_bottom + scenario["dh"]])
    # canopy held spread above the payload with the lines just short of taut
    rc = float(np.mean(np.linalg.norm(g_fab.attach_points, axis=1)))
    ra = float(np.mean(np.linalg.norm(anchors[:, :2], axis=1)))
    h = math.sqrt(max(L.min() ** 2 - (rc - ra) ** 2, 1e-6)) * 0.995
    c0 = p0 + Rm @ np.array([0, 0, float(anchors[:, 2].mean()) + h])

    xml = build_mjcf(g_fab, cfg, L, p0, qp, c0, qp)
    m = mujoco.MjModel.from_xml_string(xml.replace(f'timestep="{cfg_p["timestep"]}"', f'timestep="{dt}"'))
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    aero = AeroModel(m, params, cfg, scenario, rho)

    pid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "payload")
    pcol = np.array([g for g in range(m.ngeom) if (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or "").startswith("pcol")])
    ground_arr = np.array([mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, n) for n in ("ground", "pad")])
    sid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "imu")
    acc_adr = m.sensor_adr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SENSOR, "acc")]
    gyr_adr = m.sensor_adr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SENSOR, "gyro")]

    hold = float(dr["hold_s"])
    T = end_time(cfg)
    n_hold = int(round(hold / dt))
    n_fly = int(round((T - hold) / dt))
    N = n_hold + n_fly
    out = {
        "t": np.arange(N) * dt,
        "qpos": np.zeros((N, m.nq)),
        "v_box": np.zeros((N, 3)), "w_box": np.zeros((N, 3)),
        "acc": np.zeros((N, 3)), "gyro": np.zeros((N, 3)),
        "K": np.zeros(N), "contact": np.zeros(N, bool),
        "ten_len": np.zeros((N, m.ntendon)), "ten_active": np.zeros((N, m.ntendon), bool),
    }
    # hold phase: stationary, true specific force = R_site^T [0,0,g]
    Rs = d.site_xmat[sid].reshape(3, 3)
    f_hold = Rs.T @ np.array([0, 0, cfg_p["g"]])
    out["qpos"][:n_hold] = d.qpos
    out["acc"][:n_hold] = f_hold
    out["K"][:n_hold] = aero.K(0)
    out["ten_len"][:n_hold] = d.ten_length
    # release
    d.qvel[0:3] = v0
    d.qvel[6:9] = v0
    v6 = np.zeros(6)
    contact_t = None
    for k in range(n_fly):
        i = n_hold + k
        mujoco.mj_step1(m, d)  # positions/velocities/contacts at time d.time
        out["qpos"][i] = d.qpos
        mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, pid, v6, 0)
        out["v_box"][i] = v6[3:]
        out["w_box"][i] = v6[:3]
        out["ten_len"][i] = d.ten_length
        if d.ncon:
            gg = d.contact.geom[: d.ncon]
            g0, g1 = gg[:, 0], gg[:, 1]
            ga, gb = ground_arr
            hit = (np.isin(g0, pcol) & ((g1 == ga) | (g1 == gb))) | (np.isin(g1, pcol) & ((g0 == ga) | (g0 == gb)))
            if hit.any():
                out["contact"][i] = True
                if contact_t is None:
                    contact_t = out["t"][i]
        K = aero.apply(d, d.time, dt)
        if vertical_only:
            d.xfrc_applied[:, :2] = 0
            d.xfrc_applied[:, 3:] = 0
        mujoco.mj_step2(m, d)  # acc-stage sensors for the same state, then integrate
        out["acc"][i] = d.sensordata[acc_adr:acc_adr + 3]
        out["gyro"][i] = d.sensordata[gyr_adr:gyr_adr + 3]
        out["K"][i] = K
        if vertical_only:
            d.qvel[3:6] = 0
            d.qvel[9:12] = 0
    out["ten_active"] = out["ten_len"] >= m.tendon_range[:, 1][None, :] - 1e-9
    out.update({
        "model": m, "xml": xml, "dt": dt, "hold_s": hold, "T": T, "release_t": hold,
        "contact_t": contact_t, "deployed": bool(aero.deployed), "aero_params": params, "aero_version": aver,
        "K_i": aero.K_i, "K_o": aero.K_o, "rho": rho, "line_lengths": L, "geometry_nominal": g_nom,
        "geometry_fab": g_fab, "f_hold": f_hold,
    })
    return out
