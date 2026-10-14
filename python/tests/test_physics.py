import copy

import mujoco
import numpy as np
from scipy.integrate import solve_ivp

from chutesim.geometry import Design, build_geometry
from chutesim.physics import simulate_physics
from chutesim.scenario import sample_scenario
from chutesim.scene import build_mjcf


def _vertical_scenario(cfg):
    sc = sample_scenario(1000, cfg)
    sc.update(dict(dh=0.0, dxy=[0, 0], wind=[0, 0], line_len_err=[0.0] * 8, area_err=0.0, rho_frac=0.0,
                   deploy_u=1.0, slit_len_err_m=0.0, yaw=0.0))
    return sc


def test_fluid_model_disabled_drag_counted_once(cfg):
    g = build_geometry(Design(4, 0.1, 0.45), cfg)
    xml = build_mjcf(g, cfg, np.full(8, 0.35), [0, 0, 2], [1, 0, 0, 0], [0, 0, 2.5], [1, 0, 0, 0])
    m = mujoco.MjModel.from_xml_string(xml)
    assert m.opt.density == 0 and m.opt.viscosity == 0
    # with every explicit aero coefficient zeroed, the fall is exactly free fall (no hidden drag)
    c = copy.deepcopy(cfg)
    c["payload"]["Cd_box"] = 0.0
    sc = _vertical_scenario(c)
    sc["k_initial_frac"] = 0.0
    sc["area_err"] = -1.0          # K_open -> 0
    r = simulate_physics(Design(4, 0.1, 0.45), sc, c, vertical_only=True)
    i = np.searchsorted(r["t"], r["release_t"] + 0.3)
    vz = r["v_box"][i, 2]
    assert abs(vz + c["physics"]["g"] * (r["t"][i] - r["release_t"])) < 0.01


def test_slack_lines_do_not_push(cfg):
    """Spatial tendons limit separation only: a slack line exerts no force, and bodies may approach."""
    g = build_geometry(Design(4, 0.1, 0.45), cfg)
    xml = build_mjcf(g, cfg, np.full(8, 0.35), [0, 0, 2], [1, 0, 0, 0], [0, 0, 2.2], [1, 0, 0, 0])
    xml = xml.replace('gravity="0 0 -9.81"', 'gravity="0 0 0"')
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    d.qvel[8] = -0.5                      # canopy moves toward the payload
    for _ in range(100):
        mujoco.mj_step(m, d)
        assert not np.any(d.efc_type == mujoco.mjtConstraint.mjCNSTR_LIMIT_TENDON)
    assert abs(d.qvel[8] + 0.5) < 1e-9 and abs(d.qvel[2]) < 1e-9
    # taut: pulling apart engages the limit
    d2 = mujoco.MjData(m)
    d2.qpos[9] += 0.3
    mujoco.mj_forward(m, d2)
    assert np.any(d2.efc_type == mujoco.mjtConstraint.mjCNSTR_LIMIT_TENDON)


def test_lines_slack_during_some_flight(cfg):
    r = simulate_physics(Design(4, 0.15, 0.45), sample_scenario(1000, cfg), cfg)
    fl = (r["t"] > r["release_t"]) & (r["t"] < r["contact_t"])
    assert (~r["ten_active"][fl]).any() and r["ten_active"][fl].any()


def _ode_landing(r, cfg):
    m = cfg["payload"]["mass_kg"] + cfg["canopy"]["mass_kg"]
    from chutesim.payload import frontal_area
    Kbox = cfg["payload"]["Cd_box"] * frontal_area(cfg["payload"])
    Ki, Ko, tau, rho, g = r["K_i"], r["K_o"], r["aero_params"]["tau_s"], r["rho"], cfg["physics"]["g"]
    z0 = r["qpos"][0, 2]
    target = cfg["contact"]["pad_size_m"][2] - cfg["payload"]["extent_min_m"][2]
    def f(t, y):
        K = Ki + (Ko - Ki) * (1 - np.exp(-t / tau))
        return [-y[1], g - 0.5 * rho * (K + Kbox) * y[1] * abs(y[1]) / m]
    ev = lambda t, y: y[0] - target
    ev.terminal = True
    s = solve_ivp(f, [0, 5], [z0, 0.0], events=ev, rtol=1e-10, atol=1e-12)
    return s.y_events[0][0][1]


def test_mujoco_matches_ode(cfg):
    sc = _vertical_scenario(cfg)
    r = simulate_physics(Design(4, 0.15, 0.45), sc, cfg, vertical_only=True)
    i = np.searchsorted(r["t"], r["contact_t"]) - 1
    v_mj = -r["v_box"][i, 2]
    v_ode = _ode_landing(r, cfg)
    assert abs(v_mj - v_ode) / v_ode < 0.01, (v_mj, v_ode)


def test_timestep_convergence(cfg):
    sc = sample_scenario(1000, cfg)
    out = []
    for dt in (0.001, 0.0005):
        r = simulate_physics(Design(4, 0.15, 0.45), sc, cfg, timestep=dt)
        i = np.searchsorted(r["t"], r["contact_t"]) - 1
        out.append(-r["v_box"][i, 2])
    assert abs(out[0] - out[1]) / out[1] < 0.01, out
