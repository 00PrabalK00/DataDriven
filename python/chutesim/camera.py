"""Virtual Intel RealSense (D435i-like) RGB-D stream.

RGB: rendered from the colour imager, motion blur by averaging sub-frames over the exposure, sensor
noise, JPEG. Depth: rendered from the left-IR (depth) imager; stereo shadow invalidation using a
second render from the right-IR imager (pixels the right imager cannot see get depth 0), depth noise
growing with z^2, flying pixels at discontinuities, random holes, range limits, 1 mm quantization.
RGB and depth have separate (phase-shifted, jittered) timestamps and independent frame drops.
Depth is stored as raw z16 frames (.npy, uint16 mm) in the depth imager frame; alignment to colour is done
by the shared pipeline, which is where occlusion/alignment gaps appear.
"""
from __future__ import annotations

import os

os.environ.setdefault("MUJOCO_GL", "egl")

import cv2
import mujoco
import numpy as np

from .scene import camera_poses
from .sensors import led_on


def _rot_err(r):
    R = np.zeros(9)
    q = np.zeros(4)
    mujoco.mju_axisAngle2Quat(q, np.asarray(r) / max(np.linalg.norm(r), 1e-12), float(np.linalg.norm(r)))
    mujoco.mju_quat2Mat(R, q)
    return R.reshape(3, 3)


def calibration(cfg: dict, scenario: dict | None) -> dict:
    """What a calibration procedure would report (with calibration error if a scenario is given).
    OpenCV conventions: camera looks along +z, x right, y down; T_world_color maps colour-camera
    coordinates to world."""
    cam = cfg["camera"]
    p = camera_poses(cfg)
    R_wc = np.column_stack([p["right"], -p["up"], p["forward"]])
    t_wc = np.asarray(p["color"], float)
    if scenario is not None:
        R_wc = _rot_err(scenario["cam_rot_err"]) @ R_wc
        t_wc = t_wc + np.asarray(scenario["cam_trans_err"])

    def intr(c):
        return {"width": c["width"], "height": c["height"], "fx": c["fx"], "fy": c["fy"], "cx": c["cx"], "cy": c["cy"],
                "dist": [0.0, 0.0, 0.0, 0.0, 0.0]}

    return {
        "color": intr(cam["color"]), "depth": intr(cam["depth"]),
        "depth_unit_m": cam["depth"]["unit_m"],
        "T_color_depth": {"R": np.eye(3).tolist(), "t": [-cam["depth_to_color_m"][0], 0.0, 0.0]},
        "T_world_color": {"R": R_wc.tolist(), "t": t_wc.tolist()},
        "stream": {"color_fps": cam["color"]["fps"], "depth_fps": cam["depth"]["fps"], "model": cam["model"]},
    }


class RealSenseSim:
    def __init__(self, model, cfg):
        self.m = model
        self.cfg = cfg
        cc = cfg["camera"]
        self.d = mujoco.MjData(model)
        self.rgb_r = mujoco.Renderer(model, cc["color"]["height"], cc["color"]["width"])
        self.dep_r = mujoco.Renderer(model, cc["depth"]["height"], cc["depth"]["width"])
        self.dep_r.enable_depth_rendering()
        self.led_mat = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_MATERIAL, "led")
        dh, dw = cc["depth"]["height"], cc["depth"]["width"]
        self._u = np.broadcast_to(np.arange(dw, dtype=np.float32)[None, :], (dh, dw))

    def close(self):
        self.rgb_r.close()
        self.dep_r.close()

    def _set(self, phys, t, led):
        i = int(np.clip(round(t / phys["dt"]), 0, len(phys["t"]) - 1))
        self.d.qpos[:] = phys["qpos"][i]
        mujoco.mj_forward(self.m, self.d)
        if led:
            self.m.mat_rgba[self.led_mat] = [0.05, 1.0, 0.05, 1]
            self.m.mat_emission[self.led_mat] = 1.0
        else:
            self.m.mat_rgba[self.led_mat] = [0.12, 0.2, 0.12, 1]
            self.m.mat_emission[self.led_mat] = 0.0
        return i

    def render_rgb(self, phys, t, scenario):
        cc = self.cfg["camera"]
        n = max(int(cc["blur_subframes"]), 1)
        ts = t + (np.arange(n) + 0.5) / n * cc["exposure_s"] - cc["exposure_s"] / 2 if n > 1 else np.array([t])
        acc = None
        keys = []
        for tt in ts:
            led = bool(led_on(tt, scenario, self.cfg))
            i = self._set(phys, tt, led)
            keys.append((i, led))
            self.rgb_r.update_scene(self.d, camera="color")
            img = self.rgb_r.render().astype(np.float32)
            acc = img if acc is None else acc + img
        return acc / len(ts), keys

    def render_depth_pair(self, phys, t, scenario):
        self._set(phys, t, False)
        self.dep_r.update_scene(self.d, camera="depth")
        zl = self.dep_r.render().copy()
        self.dep_r.update_scene(self.d, camera="rir")
        zr = self.dep_r.render().copy()
        return zl, zr

    def depth_prep(self, zl, zr):
        """Deterministic part of the depth model (depends only on the rendered pair): range validity,
        stereo shadow, depth-discontinuity map. Cached across identical (static) frames."""
        dc = self.cfg["camera"]["depth"]
        h, w = zl.shape
        fx, B = dc["fx"], dc["baseline_m"]
        z = zl.astype(np.float32)
        valid = (z > dc["min_m"]) & (z < dc["max_m"])
        # stereo shadow: the right imager must see the same surface
        ur = np.rint(self._u - fx * B / np.maximum(z, 1e-3)).astype(np.int32)
        inside = (ur >= 0) & (ur < w)
        zr_s = np.take_along_axis(zr, np.clip(ur, 0, w - 1), axis=1)
        valid &= inside & (np.abs(zr_s - z) < 0.02 + 0.01 * z)
        # flying pixels at depth discontinuities (mixed foreground/background returns)
        jump = np.zeros((h, w), bool)
        jump[:, :-1] = np.abs(z[:, 1:] - z[:, :-1]) > 0.05
        jump[:-1, :] |= np.abs(z[1:, :] - z[:-1, :]) > 0.05
        zn = np.empty_like(z)
        zn[:, :-1] = z[:, 1:]
        zn[:, -1] = z[:, -1]
        k = np.float32(dc["subpixel"] / (fx * B))
        return {"z": z, "valid": valid, "jump": jump, "zmix": 0.5 * (z + zn), "zsd": z * z * k}

    def depth_imperfections(self, zl, zr, rng, prep=None):
        dc = self.cfg["camera"]["depth"]
        h, w = zl.shape
        if prep is None:
            prep = self.depth_prep(zl, zr)
        bank = _noise_bank((h, w))
        u1 = bank["u"][rng.integers(len(bank["u"]))]
        fly = prep["jump"] & (u1 < dc["flying_pixel_prob"])
        if fly.any():
            z = np.where(fly, prep["zmix"], prep["z"])
            zsd = np.where(fly, prep["zmix"] ** 2 * np.float32(dc["subpixel"] / (dc["fx"] * dc["baseline_m"])), prep["zsd"])
        else:
            z, zsd = prep["z"], prep["zsd"]
        # noise ~ z^2 (stereo subpixel error)
        z = z + bank["n"][rng.integers(len(bank["n"]))] * zsd
        u2 = bank["u"][rng.integers(len(bank["u"]))]
        valid = prep["valid"] & (np.roll(u2, int(rng.integers(w)), axis=1) >= dc["random_hole_prob"])
        out = np.where(valid, np.rint(z / dc["unit_m"]), 0)
        return np.clip(out, 0, 65535).astype(np.uint16)

    def capture(self, phys, scenario, out_dir, write=True):
        """Render the full RGB-D stream; write frames + timestamp CSVs. Returns stats."""
        cc = self.cfg["camera"]
        rng = np.random.default_rng(scenario["cam_seed"])
        T = phys["t"][-1]
        fps = cc["color"]["fps"]
        t0 = rng.uniform(0, 1 / fps)
        nf = int(np.floor((T - t0 - cc["depth_phase_s"] - 0.01) * fps))
        tn = t0 + np.arange(nf) / fps
        t_rgb = tn + rng.normal(0, cc["frame_jitter_sd_s"], nf)
        t_dep = tn + cc["depth_phase_s"] + rng.normal(0, cc["frame_jitter_sd_s"], nf)
        keep_rgb = rng.uniform(size=nf) >= cc["frame_drop_prob"]
        keep_dep = rng.uniform(size=nf) >= cc["frame_drop_prob"]
        if write:
            os.makedirs(os.path.join(out_dir, "rgb"), exist_ok=True)
            os.makedirs(os.path.join(out_dir, "depth"), exist_ok=True)
        rgb_rows, dep_rows = [], []
        last_key, last_img = None, None
        last_dkey, last_dep = None, None
        jpg = [cv2.IMWRITE_JPEG_QUALITY, int(cc["jpeg_quality"])]
        n_render = 0
        for k in range(nf):
            if keep_rgb[k]:
                tt = float(np.clip(t_rgb[k], 0, T))
                # identical state + LED across the exposure => identical image (static stretches)
                cc_n = max(int(cc["blur_subframes"]), 1)
                ts = tt + (np.arange(cc_n) + 0.5) / cc_n * cc["exposure_s"] - cc["exposure_s"] / 2
                key = tuple((int(np.clip(round(x / phys["dt"]), 0, len(phys["t"]) - 1)), bool(led_on(x, scenario, self.cfg))) for x in ts)
                key = _state_key(phys, key)
                if key == last_key:
                    img = last_img
                else:
                    img, _ = self.render_rgb(phys, tt, scenario)
                    n_render += 1
                    last_key, last_img = key, img
                bank = _noise_bank(img.shape)
                nz = bank["n"][rng.integers(len(bank["n"]))]
                noisy = np.clip(img + np.float32(cc["rgb_noise_sd"]) * nz, 0, 255).astype(np.uint8)
                if write:
                    cv2.imwrite(os.path.join(out_dir, "rgb", f"{k:06d}.jpg"), noisy[:, :, ::-1], jpg)
                rgb_rows.append((k, scenario["host_offset"] + tt))
            if keep_dep[k]:
                tt = float(np.clip(t_dep[k], 0, T))
                i = int(np.clip(round(tt / phys["dt"]), 0, len(phys["t"]) - 1))
                dkey = _state_key(phys, ((i, False),))
                if dkey == last_dkey:
                    zl, zr, prep = last_dep
                else:
                    zl, zr = self.render_depth_pair(phys, tt, scenario)
                    prep = self.depth_prep(zl, zr)
                    last_dkey, last_dep = dkey, (zl, zr, prep)
                dimg = self.depth_imperfections(zl, zr, rng, prep)
                if write:
                    np.save(os.path.join(out_dir, "depth", f"{k:06d}.npy"), dimg)
                dep_rows.append((k, scenario["host_offset"] + tt))
        if write:
            np.savetxt(os.path.join(out_dir, "rgb_times.csv"), np.array(rgb_rows), delimiter=",",
                       header="frame,t_host", comments="", fmt=["%d", "%.6f"])
            np.savetxt(os.path.join(out_dir, "depth_times.csv"), np.array(dep_rows), delimiter=",",
                       header="frame,t_host", comments="", fmt=["%d", "%.6f"])
        return {"n_frames": nf, "n_rgb": len(rgb_rows), "n_depth": len(dep_rows), "n_rgb_renders": n_render}


_BANKS: dict = {}


def _noise_bank(shape, n: int = 8) -> dict:
    """Per-process bank of independent noise fields (float32); a frame draws one at random.
    Pixel noise is independent within a frame; reuse across frames is a documented approximation."""
    key = tuple(shape)
    if key not in _BANKS:
        r = np.random.default_rng(12345)
        _BANKS[key] = {"n": [r.standard_normal(shape, dtype=np.float32) for _ in range(n)],
                       "u": [r.random(shape[:2], dtype=np.float32) for _ in range(n)]}
    return _BANKS[key]


def _state_key(phys, idx_led):
    q = phys["qpos"]
    return tuple((np.round(q[i], 7).tobytes(), led) for i, led in idx_led)
