"""Validation process: the ONLY code that reads simulator truth. Compares pipeline estimates
(obs-derived) with truth after the fact. Run separately from the estimation worker.

  python -m validation.compare RUN_ROOT TRIAL_ID [--est EST_ROOT]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def load_truth(run_root: Path, trial: str):
    td = run_root / "truth" / trial
    with open(td / "truth.json") as f:
        tj = json.load(f)
    tz = dict(np.load(td / "truth.npz"))
    return tj, tz


def truth_at(tz, t_sim):
    i = np.clip(np.rint(np.asarray(t_sim) / (tz["t"][1] - tz["t"][0])).astype(int), 0, len(tz["t"]) - 1)
    return i


def to_sim_time(t, clock, tj):
    if clock == "host":
        return np.asarray(t) - tj["host_offset"]
    return (np.asarray(t) - tj["mcu_offset"]) / (1 + tj["mcu_drift_ppm"] * 1e-6)


def compare(run_root: str | Path, trial: str, est_root: str | Path | None = None) -> dict:
    run_root = Path(run_root)
    est = Path(est_root) if est_root else run_root / "est"
    tj, tz = load_truth(run_root, trial)
    with open(est / trial / "metrics.json") as f:
        m = json.load(f)
    t_c = tj["contact_t_sim"]
    dt = tz["t"][1] - tz["t"][0]
    ic = int(round(t_c / dt))
    guard = 0.01
    ig = ic - int(round(guard / dt))
    true_vz = float(-tz["v_box"][ig, 2])
    true_lat = float(np.hypot(*tz["v_box"][ig, :2]))
    out = {"trial": trial, "true": {"contact_t_sim": t_c, "preimpact_vz": true_vz, "lateral_speed": true_lat,
                                    "deployed": tj["deployed"]}, "modes": {}}
    if m["sync"]["status"] == "ok":
        true_b = tj["host_offset"] - tj["mcu_offset"]
        out["sync_offset_err_s"] = m["sync"]["b"] - true_b
    for mode, mm in m["modes"].items():
        r = {}
        clock = mm.get("clock", "host")
        if mm.get("contact_t") is not None:
            r["contact_t_err_s"] = float(to_sim_time(mm["contact_t"], clock, tj) - t_c)
        v = mm["preimpact_vz"]
        r["preimpact_vz_status"] = v["status"]
        if v["value"] is not None:
            r["preimpact_vz_err"] = v["value"] - true_vz
        ls = mm["lateral_speed"]
        if ls["value"] is not None:
            r["lateral_speed_err"] = ls["value"] - true_lat
        r["decel"] = mm["decel"]["value"]
        tp = est / trial / f"traj_{mode}.npz"
        if tp.exists():
            tr = np.load(tp)
            if len(tr["t"]):
                ts = to_sim_time(tr["t"], clock, tj)
                sel = (ts > tj["release_t_sim"] + 0.05) & (ts < t_c - guard)
                if sel.any():
                    idx = truth_at(tz, ts[sel])
                    e = tr["p"][sel] - tz["qpos"][idx, :3]
                    r["pos_rmse_flight_m"] = np.sqrt(np.mean(e**2, axis=0)).tolist()
                    if "v" in tr and len(tr["v"]) == len(tr["t"]):
                        ev = tr["v"][sel] - tz["v_box"][idx]
                        r["vel_rmse_flight_mps"] = np.sqrt(np.mean(ev**2, axis=0)).tolist()
                    r["n_flight_samples"] = int(sel.sum())
        out["modes"][mode] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_root")
    ap.add_argument("trial")
    ap.add_argument("--est")
    a = ap.parse_args()
    print(json.dumps(compare(a.run_root, a.trial, a.est), indent=1))


if __name__ == "__main__":
    main()
