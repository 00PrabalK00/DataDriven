"""Simulate one drop and write: observation bundle (obs/<trial>), truth (truth/<trial>, separate
root marked with a .TRUTH_ROOT sentinel) and a manifest (manifest/<trial>.json) with seeds/provenance.

The observation bundle has the same layout a real recording will have (no truth inside).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from .camera import RealSenseSim, calibration
from .config import canonical_json
from .geometry import Design
from .physics import simulate_physics
from .provenance import component_hashes, environment
from .scenario import sample_scenario
from .scene import led_layout, marker_corners_box, marker_layout
from .sensors import imu_observations

TRUTH_SENTINEL = ".TRUTH_ROOT"


def rig_description(cfg: dict) -> dict:
    """Protocol/rig knowledge available to the pipeline in sim and real (not truth)."""
    pc, dr = cfg["payload"], cfg["drop"]
    z_bottom = -pc["extent_min_m"][2]
    return {
        "payload_model": pc["model"],
        "extent_min_m": pc["extent_min_m"], "extent_max_m": pc["extent_max_m"],
        "mass_kg": pc["mass_kg"], "Cd_box": pc["Cd_box"],
        "imu_offset_m": pc["imu_offset_m"], "imu_mount_rpy_deg": pc["imu_mount_rpy_deg"],
        "markers": [{"id": m["id"], "size_m": m["size"], "corners_box_m": marker_corners_box(m).tolist(),
                     "center_box_m": m["center"].tolist(), "normal_box_m": m["normal"].tolist()}
                    for m in marker_layout(cfg)],
        "marker_dictionary": pc["marker_dictionary"],
        "leds_box_m": [l["center"].tolist() for l in led_layout(cfg)],
        "box_color_rgb": pc["color_rgb"],
        "pad_top_z_m": cfg["contact"]["pad_size_m"][2],
        "release_nominal_m": [dr["release_xy_m"][0], dr["release_xy_m"][1], dr["height_m"] + z_bottom],
        "g": cfg["physics"]["g"], "rho_nominal": cfg["physics"]["rho"],
    }


def write_drop(design: Design, seed: int, cfg: dict, run_root: str | Path, trial_id: str,
               render: bool = True, timestep: float | None = None) -> dict:
    run_root = Path(run_root)
    obs = run_root / "obs" / trial_id
    truth_root = run_root / "truth"
    truth = truth_root / trial_id
    man = run_root / "manifest"
    for p in (obs, truth, man):
        p.mkdir(parents=True, exist_ok=True)
    (truth_root / TRUTH_SENTINEL).touch()

    sc = sample_scenario(seed, cfg)
    phys = simulate_physics(design, sc, cfg, timestep=timestep)
    imu = imu_observations(phys, sc, cfg)

    # --- observations ---
    np.savetxt(obs / "imu.csv", np.column_stack([imu["t_mcu"], imu["acc"], imu["gyro"]]), delimiter=",",
               header="t_mcu,ax,ay,az,gx,gy,gz", comments="", fmt="%.6f")
    np.savetxt(obs / "led_events.csv", imu["led_events"], delimiter=",", header="t_mcu,state", comments="",
               fmt=["%.6f", "%d"])
    with open(obs / "calib.json", "w") as f:
        json.dump(calibration(cfg, sc), f, indent=1)
    meta = {
        "source": "sim", "trial_id": trial_id,
        "design": {"q": design.q, "slit_len": design.slit_len, "slit_r": design.slit_r,
                   "radial": list(design.radial) if design.radial is not None else None},
        "rig": rig_description(cfg),
        "led_code": cfg["drop"]["led_code"],
        "imu": {"rate_hz": cfg["imu"]["rate_hz"], "accel_range_mps2": cfg["imu"]["accel_range_mps2"],
                "gyro_range_rps": cfg["imu"]["gyro_range_rps"]},
    }
    with open(obs / "meta.json", "w") as f:
        json.dump(meta, f, indent=1)
    cam_stats = {}
    if render:
        cam = RealSenseSim(phys["model"], cfg)
        try:
            cam_stats = cam.capture(phys, sc, str(obs))
        finally:
            cam.close()

    # --- truth (separate root) ---
    np.savez_compressed(truth / "truth.npz", t=phys["t"], qpos=phys["qpos"], v_box=phys["v_box"], w_box=phys["w_box"],
                        acc=phys["acc"], gyro=phys["gyro"], K=phys["K"], contact=phys["contact"],
                        ten_len=phys["ten_len"], ten_active=phys["ten_active"],
                        imu_t_sim=imu["truth_t_sim"], imu_bias_acc=imu["truth_bias_acc"],
                        imu_bias_gyro=imu["truth_bias_gyro"])
    tj = {
        "release_t_sim": phys["release_t"], "contact_t_sim": phys["contact_t"], "deployed": phys["deployed"],
        "K_i": phys["K_i"], "K_o": phys["K_o"], "rho": phys["rho"], "aero_params": phys["aero_params"],
        "mcu_offset": sc["mcu_offset"], "mcu_drift_ppm": sc["mcu_drift_ppm"], "host_offset": sc["host_offset"],
        "calib_true": calibration(cfg, None), "geometry_nominal": phys["geometry_nominal"].to_dict(),
    }
    with open(truth / "truth.json", "w") as f:
        f.write(canonical_json(tj))
    with open(truth / "model.xml", "w") as f:
        f.write(phys["xml"])

    manifest = {
        "trial_id": trial_id, "seed": int(seed), "scenario": sc, "design": meta["design"],
        "components": component_hashes(cfg, phys["aero_version"]), "environment": environment(),
        "timestep": phys["dt"], "camera": cam_stats, "evidence_level": "L2",
    }
    with open(man / f"{trial_id}.json", "w") as f:
        json.dump(manifest, f, indent=1, default=float)
    return {"obs": str(obs), "truth": str(truth), "manifest": manifest, "phys": phys}
