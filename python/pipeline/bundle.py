"""Observation bundle reader (identical for simulated and real recordings).

Truth separation is LOGICAL, not a security boundary: the worker runs as the same OS user. It is
enforced by (1) refusing any path inside a directory tree marked with a .TRUTH_ROOT sentinel,
(2) never receiving a truth path, and (3) leakage tests (audit hook on open(), byte-identical metrics
with the truth root removed).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

TRUTH_SENTINEL = ".TRUTH_ROOT"


class TruthAccessError(PermissionError):
    pass


def guard_path(path: str | Path) -> Path:
    p = Path(path).resolve()
    for d in [p, *p.parents]:
        if (d / TRUTH_SENTINEL).exists():
            raise TruthAccessError(f"refusing path inside a truth root: {p}")
    return p


@dataclass
class Bundle:
    root: Path
    meta: dict
    calib: dict
    imu: np.ndarray          # (N,7): t_mcu, ax, ay, az, gx, gy, gz
    led_events: np.ndarray   # (M,2): t_mcu, state
    rgb_times: np.ndarray    # (F,2): frame, t_host
    depth_times: np.ndarray  # (F,2): frame, t_host

    def rgb_path(self, frame: int) -> Path:
        return self.root / "rgb" / f"{int(frame):06d}.jpg"

    def depth_path(self, frame: int) -> Path:
        return self.root / "depth" / f"{int(frame):06d}.npy"

    def read_rgb(self, frame: int) -> np.ndarray:
        import cv2
        img = cv2.imread(str(guard_path(self.rgb_path(frame))), cv2.IMREAD_COLOR)
        return img  # BGR

    def read_depth(self, frame: int) -> np.ndarray:
        return np.load(guard_path(self.depth_path(frame)))


def _csv(path: Path, ncols: int) -> np.ndarray:
    if not path.exists():
        return np.zeros((0, ncols))
    a = np.loadtxt(guard_path(path), delimiter=",", skiprows=1, ndmin=2)
    return a.reshape(-1, ncols)


def load_bundle(path: str | Path) -> Bundle:
    root = guard_path(path)
    with open(guard_path(root / "meta.json")) as f:
        meta = json.load(f)
    with open(guard_path(root / "calib.json")) as f:
        calib = json.load(f)
    return Bundle(root, meta, calib, _csv(root / "imu.csv", 7), _csv(root / "led_events.csv", 2),
                  _csv(root / "rgb_times.csv", 2), _csv(root / "depth_times.csv", 2))
