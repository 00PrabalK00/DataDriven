"""Replay video of one simulated drop: [overview 3D render | virtual RealSense RGB + detections |
raw depth]. Visualization only (it reads simulator truth for the overview panel, so it is NOT part of
the estimation pipeline).

  uv run python ../scripts/make_replay_video.py RUN_ROOT TRIAL OUT.mp4 [--slowmo 4]
"""
import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import cv2
import mujoco
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_root")
    ap.add_argument("trial")
    ap.add_argument("out")
    ap.add_argument("--slowmo", type=float, default=4.0)
    a = ap.parse_args()
    root = Path(a.run_root)
    obs, tru, est = root / "obs" / a.trial, root / "truth" / a.trial, root / "est" / a.trial
    tj = json.load(open(tru / "truth.json"))
    tz = np.load(tru / "truth.npz")
    m = mujoco.MjModel.from_xml_string((tru / "model.xml").read_text())
    d = mujoco.MjData(m)
    H, W = 480, 640
    ren = mujoco.Renderer(m, H, W)
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.distance, cam.elevation, cam.azimuth = 1.6, -12.0, 60.0
    rgb_t = np.loadtxt(obs / "rgb_times.csv", delimiter=",", skiprows=1)
    dep_t = np.loadtxt(obs / "depth_times.csv", delimiter=",", skiprows=1)
    det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    met = json.load(open(est / "metrics.json")) if (est / "metrics.json").exists() else None
    fused = np.load(est / "traj_fused.npz") if (est / "traj_fused.npz").exists() else None
    calib = json.load(open(obs / "calib.json"))
    Rwc, twc = np.array(calib["T_world_color"]["R"]), np.array(calib["T_world_color"]["t"])
    K = np.array([[calib["color"]["fx"], 0, calib["color"]["cx"]], [0, calib["color"]["fy"], calib["color"]["cy"]], [0, 0, 1]])
    fps_out = 60.0 / a.slowmo
    vw = cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"mp4v"), fps_out, (W + 2 * 424, H))
    dt = tz["t"][1] - tz["t"][0]
    for k, th in rgb_t:
        ts = th - tj["host_offset"]
        i = int(np.clip(round(ts / dt), 0, len(tz["t"]) - 1))
        d.qpos[:] = tz["qpos"][i]
        mujoco.mj_forward(m, d)
        cam.lookat[:] = [d.qpos[0], d.qpos[1], 0.5 * (d.qpos[2] + d.qpos[9])]
        ren.update_scene(d, camera=cam)
        ov = ren.render()[:, :, ::-1].copy()
        cv2.putText(ov, f"t = {ts - tj['release_t_sim']:+.3f} s from release", (10, 25), 0, 0.6, (255, 255, 255), 2)
        cv2.putText(ov, f"true vz = {tz['v_box'][i, 2]:+.2f} m/s", (10, 50), 0, 0.6, (255, 255, 255), 2)
        cv2.putText(ov, "overview (simulator view)", (10, H - 12), 0, 0.5, (200, 200, 200), 1)
        img = cv2.imread(str(obs / "rgb" / f"{int(k):06d}.jpg"))
        corners, ids, _ = det.detectMarkers(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        if ids is not None:
            cv2.aruco.drawDetectedMarkers(img, corners, ids)
        if fused is not None:
            sel = (fused["t"] <= th)
            if sel.any():
                P = fused["p"][sel][::4]
                pc = (Rwc.T @ (P - twc).T).T
                uv = (K @ pc.T).T
                uv = uv[:, :2] / uv[:, 2:3]
                for p in uv.astype(int):
                    cv2.circle(img, tuple(p), 1, (255, 255, 0), -1)
        g = img[..., 1].astype(int); r_ = img[..., 2].astype(int)
        led = int(((g > 200) & (r_ < 120)).sum()) >= 6
        cv2.putText(img, "virtual RealSense RGB", (8, 22), 0, 0.6, (255, 255, 255), 2)
        cv2.putText(img, f"markers: {0 if ids is None else len(ids)}   LED: {'ON' if led else 'off'}", (8, 46), 0, 0.55,
                    (0, 255, 0) if led else (255, 255, 255), 2)
        cv2.putText(img, "cyan = fused trajectory estimate", (8, 470), 0, 0.45, (255, 255, 0), 1)
        img = cv2.resize(img, (848, 480))
        j = int(np.argmin(np.abs(dep_t[:, 1] - th)))
        dp = obs / "depth" / f"{int(dep_t[j, 0]):06d}.npy"
        if dp.exists():
            z = np.load(dp).astype(np.float32) / 1000.0
            vis = cv2.applyColorMap(np.clip((z - 0.3) / 3.0 * 255, 0, 255).astype(np.uint8), cv2.COLORMAP_TURBO)
            vis[z == 0] = 0
        else:
            vis = np.zeros((480, 848, 3), np.uint8)
        cv2.putText(vis, "raw depth (black = invalid/holes)", (8, 22), 0, 0.6, (255, 255, 255), 2)
        panel = np.hstack([img[:, :424], vis[:, 212:636]]) if False else None
        right = np.hstack([cv2.resize(img, (424, 240)), cv2.resize(vis, (424, 240))])
        right = np.vstack([right, np.zeros((240, 848, 3), np.uint8)])
        if met is not None:
            y = 270
            cv2.putText(right, "Pipeline output (sensor-derived, L1 software check):", (10, y), 0, 0.55, (255, 255, 255), 1)
            for mode in ("camera", "imu", "fused"):
                mm = met["modes"][mode]
                v = mm["preimpact_vz"]
                txt = f"{mode:7s} pre-impact speed: " + (f"{v['value']:.2f} m/s" if v["value"] is not None else v["status"])
                y += 28
                cv2.putText(right, txt, (10, y), 0, 0.55, (180, 255, 180), 1)
            iz = int(round(tj["contact_t_sim"] / dt)) - 10
            y += 28
            cv2.putText(right, f"truth  pre-impact speed: {-tz['v_box'][iz, 2]:.2f} m/s", (10, y), 0, 0.55, (180, 180, 255), 1)
            y += 28
            cv2.putText(right, "L2 assumed aerodynamics (placeholder mass/height)", (10, y), 0, 0.45, (160, 160, 160), 1)
        vw.write(np.hstack([ov, right]))
    vw.release()
    ren.close()
    print(a.out)


if __name__ == "__main__":
    main()
