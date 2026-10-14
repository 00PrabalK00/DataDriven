"""Estimation worker: observation bundle -> trajectories (camera / imu / fused) + metrics.

Shared by simulated and real data. Receives ONLY an observation-bundle path and an output path.
Run as a separate process (single shot or persistent `--serve` mode reading JSON lines on stdin).
Truth separation is logical (same OS account), enforced by guard_path + leakage tests.

  python -m pipeline.worker --obs OBS_DIR --out OUT_DIR --pipeline-config cfg.json
  python -m pipeline.worker --serve      # {"obs":..., "out":..., "pipeline_cfg": {...}} per line
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from .bundle import guard_path, load_bundle
from .detect import Detector
from .ekf import camera_only, fused, imu_only
from .geometry3d import rpy_to_R
from .metrics import (camera_contact_bracket, compute_metrics, detect_contact_traj, detect_impact_imu,
                      detect_release, extrapolate_contact, traj_contact_time)
from .sync import solve_sync

MODES = ("camera", "imu", "fused")


def process(obs_dir: str, out_dir: str, cp: dict) -> dict:
    t_start = time.time()
    b = load_bundle(obs_dir)
    out = guard_path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rig = b.meta["rig"]
    g = rig["g"]
    fps = b.calib["stream"]["color_fps"]

    meas, led, det_stats = Detector(b, cp).run()
    sync = solve_sync(led, b.led_events, fps)
    t_mcu, f_s, w_s = b.imu[:, 0], b.imu[:, 1:4], b.imu[:, 4:7]
    rng_lim = float(b.meta["imu"]["accel_range_mps2"])
    R_bs = rpy_to_R(*np.radians(rig["imu_mount_rpy_deg"]))
    t_rel_mcu = detect_release(t_mcu, f_s, cp, g) if len(t_mcu) else None
    t_imp_mcu = detect_impact_imu(t_mcu, f_s, t_rel_mcu, cp, g, rng_lim) if t_rel_mcu is not None else None

    results = {"trial_id": b.meta.get("trial_id"), "source": b.meta.get("source"), "sync": sync,
               "detection": det_stats, "modes": {}}
    trajs = {}

    # ---- camera-only ----
    br = camera_contact_bracket(meas, rig, cp["contact_height_tol_m"])
    if br is None:
        tr = camera_only(meas, b.calib, cp["cam_only"]["accel_psd"])
        ev = {"status": "invalid_contact", "reason": "camera never saw the box airborne and then on the pad"}
    else:
        t_air, t_pad, h_low = br
        tr = camera_only(meas, b.calib, cp["cam_only"]["accel_psd"], t_cut=t_pad)
        if len(tr["t"]) == 0:
            ev = {"status": "invalid_tracking", "reason": "no pre-contact camera measurements"}
        else:
            tc = extrapolate_contact(tr, rig, h_low, t_air, t_pad)
            ev = {"status": "ok", "contact_t": tc, "release_t": None}
    results["modes"]["camera"] = compute_metrics("camera", tr, ev, None, rig, cp)
    results["modes"]["camera"]["clock"] = "host"
    trajs["camera"] = tr

    # ---- IMU-only (MCU clock) ----
    imu_pack = {"t": t_mcu, "f": f_s, "w": w_s, "range": rng_lim, "R_bs": R_bs}
    if t_rel_mcu is None:
        ev = {"status": "invalid_release", "reason": "no free-fall onset found in IMU"}
        ti = None
    elif t_imp_mcu is None:
        ev = {"status": "invalid_contact", "reason": "no impact signature in IMU"}
        ti = None
    else:
        ev = {"status": "ok", "contact_t": t_imp_mcu, "release_t": t_rel_mcu}
    if t_rel_mcu is not None:
        # estimate only up to the impact onset: clipped impact data must not leak into the smoother
        cut = t_mcu <= (t_imp_mcu if t_imp_mcu is not None else np.inf)
        ti = imu_only(t_mcu[cut], f_s[cut], w_s[cut], rig, cp["ekf"], t_rel_mcu, b.calib)
        trajs["imu"] = ti
        results["modes"]["imu"] = compute_metrics("imu", ti, ev, imu_pack, rig, cp)
    else:
        results["modes"]["imu"] = compute_metrics("imu", {}, ev, imu_pack, rig, cp)
    results["modes"]["imu"]["clock"] = "mcu"

    # ---- fused (host clock) ----
    if sync["status"] != "ok":
        ev = {"status": "invalid_sync", "reason": sync.get("reason")}
        results["modes"]["fused"] = compute_metrics("fused", {}, ev, None, rig, cp)
    elif t_rel_mcu is None:
        results["modes"]["fused"] = compute_metrics("fused", {}, {"status": "invalid_release",
                                                    "reason": "no free-fall onset found in IMU"}, None, rig, cp)
    else:
        a, bb = sync["a"], sync["b"]
        th = a * t_mcu + bb
        t_rel = a * t_rel_mcu + bb
        t_imp = a * t_imp_mcu + bb if t_imp_mcu is not None else None
        if t_imp is None:
            ev = {"status": "invalid_contact", "reason": "no impact signature in IMU"}
            tf = fused(th, f_s, w_s, meas, rig, cp["ekf"], t_rel, b.calib)
        else:
            # estimate only up to the IMU impact onset (no post-impact data in the smoother)
            cut = th <= t_imp
            tf = fused(th[cut], f_s[cut], w_s[cut], [m for m in meas if m["t"] <= t_imp], rig, cp["ekf"],
                       t_rel, b.calib)
            t_trj = traj_contact_time(tf["t"], tf["p"], tf["v"], tf["R"], rig, cp["contact_height_tol_m"])
            if t_trj is None:
                ev = {"status": "invalid_contact", "reason": "fused trajectory not descending at impact"}
            elif abs(t_imp - t_trj) > cp["contact_agree_s"]:
                ev = {"status": "invalid_contact",
                      "reason": f"IMU impact and trajectory contact disagree by {abs(t_imp - t_trj):.3f}s"}
            else:
                ev = {"status": "ok", "contact_t": t_imp, "release_t": t_rel}
        trajs["fused"] = tf
        n_cam = None
        if ev["status"] == "ok":
            n_cam = sum(1 for m in meas if m["type"] in ("pnp", "fallback") and t_imp - 0.5 <= m["t"] <= t_imp)
        imu_h = dict(imu_pack, t=th)
        results["modes"]["fused"] = compute_metrics("fused", tf, ev, imu_h, rig, cp, n_cam_window=n_cam)
        results["modes"]["fused"]["n_cam_near_impact"] = n_cam
    results["modes"]["fused"]["clock"] = "host"

    for mname, trj in trajs.items():
        np.savez_compressed(out / f"traj_{mname}.npz", **{k: v for k, v in trj.items()
                                                          if isinstance(v, np.ndarray)})
    results["runtime_s"] = time.time() - t_start
    with open(out / "metrics.json", "w") as f:
        json.dump(results, f, indent=1, default=_jd)
    return results


def _jd(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(type(o))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--obs")
    ap.add_argument("--out")
    ap.add_argument("--pipeline-config")
    ap.add_argument("--serve", action="store_true")
    a = ap.parse_args(argv)
    if a.serve:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            req = json.loads(line)
            try:
                r = process(req["obs"], req["out"], req["pipeline_cfg"])
                resp = {"ok": True, "metrics": r}
            except Exception as e:  # report, never invent values
                resp = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            sys.stdout.write(json.dumps(resp, default=_jd) + "\n")
            sys.stdout.flush()
        return
    with open(a.pipeline_config) as f:
        cp = json.load(f)
    cp = cp.get("pipeline", cp)
    r = process(a.obs, a.out, cp)
    print(json.dumps({k: r[k] for k in ("sync", "detection")}, default=_jd))


if __name__ == "__main__":
    main()
