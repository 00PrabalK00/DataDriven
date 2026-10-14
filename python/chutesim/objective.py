"""Optimization score from sensor-derived metrics (identical rule for every optimizer).

Measured speeds are never clipped or altered; only the optimization SCORE is bounded:
  score = min(mean_speed, S_cap) + drift_pen + decel_pen         (all required scenarios valid)
  score = P_infeasible = S_cap + sum(penalty caps) + 1            (any required scenario invalid)
S_cap = sqrt(v0_max^2 + 2 g h_max) + margin, h_max = drop height + 3 sd. A measured speed above S_cap is
logged as an estimation anomaly, not hidden. Sensing failures and aerodynamic failures are counted
separately. The infeasibility penalty is an optimization score, never a fabricated measurement.
"""
from __future__ import annotations

import math

REQUIRED = ("preimpact_vz", "lateral_speed", "decel")


def score_bounds(cfg: dict) -> dict:
    ob, sc = cfg["objective"], cfg["scenario"]
    h_max = cfg["drop"]["height_m"] + 3 * sc["height_sd_m"]
    s_cap = math.sqrt(sc["v0_max_mps"] ** 2 + 2 * cfg["physics"]["g"] * h_max) + ob["score_cap_margin_mps"]
    p_inf = s_cap + ob["drift_weight"] * ob["drift_cap"] + ob["decel_weight"] * ob["decel_cap"] + 1.0
    return {"S_cap": s_cap, "P_infeasible": p_inf}


def score(per_scenario: list[dict], cfg: dict, mode: str = "fused") -> dict:
    """per_scenario: list of worker metrics dicts (metrics['modes'][mode] taken here)."""
    ob = cfg["objective"]
    b = score_bounds(cfg)
    vz, lat, decel = [], [], []
    sensing, aero, anomalies = [], [], []
    for i, m in enumerate(per_scenario):
        mm = m["modes"][mode] if m is not None else None
        if mm is None:
            sensing.append({"scenario": i, "metric": "all", "status": "pipeline_error"})
            continue
        bad = [(k, mm[k]["status"], mm[k].get("reason")) for k in REQUIRED if mm[k]["value"] is None]
        if bad:
            for k, st, why in bad:
                sensing.append({"scenario": i, "metric": k, "status": st, "reason": why})
            continue
        v = mm["preimpact_vz"]["value"]
        vz.append(v)
        lat.append(mm["lateral_speed"]["value"])
        decel.append(mm["decel"]["value"])
        if mm["decel"]["value"] == "no":
            aero.append({"scenario": i, "label": "effective deceleration not established"})
        if v > b["S_cap"]:
            anomalies.append({"scenario": i, "preimpact_vz": v, "S_cap": b["S_cap"]})
    n = len(per_scenario)
    out = {"n_scenarios": n, "sensing_failures": sensing,
           "sensing_failure_scenarios": len({f["scenario"] for f in sensing}), "aero_failures": aero, "anomalies": anomalies,
           "measured_preimpact_vz": vz, "measured_lateral_speed": lat, "decel_labels": decel,
           "S_cap": b["S_cap"], "P_infeasible": b["P_infeasible"], "evidence_level": "L2"}
    if sensing:
        out.update({"status": "infeasible_sensing", "score": b["P_infeasible"], "penalty_marked": True,
                    "mean_preimpact_vz": None})
        return out
    mean_v = sum(vz) / n
    mean_lat = sum(lat) / n
    no_rate = sum(1 for d in decel if d == "no") / n
    drift_pen = ob["drift_weight"] * min(max(0.0, mean_lat - ob["drift_limit_mps"]), ob["drift_cap"])
    decel_pen = ob["decel_weight"] * min(max(0.0, no_rate - ob["decel_fail_baseline"]), ob["decel_cap"])
    out.update({"status": "ok", "penalty_marked": False, "mean_preimpact_vz": mean_v,
                "mean_lateral_speed": mean_lat, "decel_no_rate": no_rate,
                "drift_penalty": drift_pen, "decel_penalty": decel_pen,
                "score": min(mean_v, b["S_cap"]) + drift_pen + decel_pen})
    return out


def geometry_infeasible(reasons: list, cfg: dict) -> dict:
    b = score_bounds(cfg)
    return {"status": "infeasible_geometry", "reasons": reasons, "score": b["P_infeasible"], "penalty_marked": True,
            "mean_preimpact_vz": None, "sensing_failures": [], "aero_failures": [], "anomalies": [],
            "S_cap": b["S_cap"], "P_infeasible": b["P_infeasible"], "evidence_level": "L2"}
