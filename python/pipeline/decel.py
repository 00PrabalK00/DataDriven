"""Observable label "effective deceleration established" in {yes, no, invalid}.

Compares the measured mean upward specific force during descent (IMU modes: world-vertical specific
force from the estimated attitude; camera-only: smoothed vertical acceleration + g) with what the box
alone would produce at the measured speeds. It never reads simulator deployment state, and it does
not claim to see canopy inflation (the simulated rigid canopy cannot show inflation).
"""
from __future__ import annotations

import numpy as np


def box_only_specific_force(v2_mean: float, rig: dict) -> float:
    lo, hi = rig["extent_min_m"], rig["extent_max_m"]
    area = (hi[0] - lo[0]) * (hi[1] - lo[1])
    return 0.5 * rig["rho_nominal"] * rig["Cd_box"] * area * v2_mean / rig["mass_kg"]


def label_from_series(f_up: np.ndarray, speed: np.ndarray, rig: dict, factor: float, min_n: int = 10) -> dict:
    if len(f_up) < min_n:
        return {"value": None, "status": "invalid_tracking", "reason": f"only {len(f_up)} samples in window"}
    f_meas = float(np.mean(f_up))
    f_box = box_only_specific_force(float(np.mean(speed**2)), rig)
    lab = "yes" if f_meas > factor * f_box else "no"
    return {"value": lab, "status": "ok", "f_up_mean": f_meas, "f_box_expected": f_box,
            "ratio": f_meas / f_box if f_box > 0 else None}
