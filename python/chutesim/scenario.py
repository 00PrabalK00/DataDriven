"""Environmental / fabrication / sensor scenarios drawn deterministically from a seed.

Search uses a fixed scenario set (common random numbers); final re-scoring uses fresh seeds.
"""
from __future__ import annotations

import math

import numpy as np


def sample_scenario(seed: int, cfg: dict) -> dict:
    sc = cfg["scenario"]
    ss = np.random.SeedSequence(int(seed))
    phys_ss, imu_ss, cam_ss, osc_ss = ss.spawn(4)
    r = np.random.default_rng(phys_ss)
    n_lines = cfg["canopy"]["n_lines"]
    v0 = r.normal(0, sc["v0_sd_mps"], 3)
    nv = np.linalg.norm(v0)
    if nv > sc["v0_max_mps"]:
        v0 *= sc["v0_max_mps"] / nv
    ri = np.random.default_rng(imu_ss)
    rc = np.random.default_rng(cam_ss)
    return {
        "seed": int(seed),
        "version": sc["version"],
        "dh": float(r.normal(0, sc["height_sd_m"])),
        "dxy": r.normal(0, sc["xy_sd_m"], 2).tolist(),
        "roll": math.radians(float(r.normal(0, sc["tilt_sd_deg"]))),
        "pitch": math.radians(float(r.normal(0, sc["tilt_sd_deg"]))),
        "yaw": float(r.uniform(0, 2 * math.pi)),
        "v0": v0.tolist(),
        "line_len_err": r.normal(0, sc["line_len_sd_m"], n_lines).tolist(),
        "area_err": float(r.normal(0, sc["area_err_sd"])),
        "slit_len_err_m": float(r.normal(0, sc["slit_len_err_sd_m"])),
        "rho_frac": float(r.normal(0, sc["rho_sd_frac"])),
        "k_initial_frac": float(r.uniform(*sc["k_initial_frac"])),
        "wind": r.normal(0, sc["wind_sd_mps"], 2).tolist(),
        "deploy_u": float(r.uniform()),
        "osc_seed": int(np.random.default_rng(osc_ss).integers(2**31)),
        "cam_rot_err": np.radians(rc.normal(0, sc["cam_calib_rot_sd_deg"], 3)).tolist(),
        "cam_trans_err": rc.normal(0, sc["cam_calib_trans_sd_m"], 3).tolist(),
        "cam_seed": int(rc.integers(2**31)),
        "host_offset": float(rc.uniform(*cfg["camera"]["host_clock_offset_s"])),
        "imu_seed": int(ri.integers(2**31)),
        "mcu_offset": float(ri.uniform(*cfg["imu"]["clock_offset_s"])),
        "mcu_drift_ppm": float(ri.normal(0, cfg["imu"]["clock_drift_ppm_sd"])),
    }
