"""Provenance: component versions/hashes for cache keys and the pinned-environment record."""
from __future__ import annotations

import functools
import hashlib
import os
import platform
import subprocess
import sys
from pathlib import Path

from .config import REPO_ROOT, source_hash, stable_hash

PY_ROOT = REPO_ROOT / "python"


@functools.lru_cache(maxsize=1)
def environment() -> dict:
    import cv2
    import mujoco
    import numpy
    import scipy
    lock = PY_ROOT / "uv.lock"
    try:
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        gpu = "unknown"
    return {
        "python": sys.version.split()[0],
        "mujoco": mujoco.__version__, "numpy": numpy.__version__, "scipy": scipy.__version__, "opencv": cv2.__version__,
        "uv_lock_sha": hashlib.sha256(lock.read_bytes()).hexdigest()[:16] if lock.exists() else None,
        "render_backend": os.environ.get("MUJOCO_GL", "egl"),
        "gpu_driver": gpu, "cpu": platform.processor() or platform.machine(), "os": platform.platform(),
    }


def environment_hash() -> str:
    return stable_hash(environment())


# files that determine what a simulated drop produces (orchestration such as bridge/cli/evaluate is excluded,
# so housekeeping edits do not invalidate finished evaluations)
SIM_FILES = ("aero.py", "aeromap.py", "camera.py", "config.py", "geometry.py", "objective.py", "payload.py",
             "physics.py", "run_drop.py", "scenario.py", "scene.py", "sensors.py")


@functools.lru_cache(maxsize=1)
def simulator_version() -> str:
    import mujoco
    h = hashlib.sha256()
    for f in SIM_FILES:
        h.update(f.encode())
        h.update((PY_ROOT / "chutesim" / f).read_bytes())
    return f"mujoco-{mujoco.__version__}+chutesim-{h.hexdigest()[:16]}"


def pipeline_version(cfg: dict) -> str:
    return f"pipeline-{source_hash(PY_ROOT / 'pipeline')}+cfg-{stable_hash(cfg['pipeline'])}"


def component_hashes(cfg: dict, aero_version: str) -> dict:
    return {
        "scenario_dist": stable_hash(cfg["scenario"]),
        "physical": stable_hash({k: cfg[k] for k in ("physics", "payload", "drop", "contact")} |
                                {"canopy": cfg["canopy"]}),
        "aero": aero_version,
        "sensors": stable_hash({"imu": cfg["imu"], "camera": cfg["camera"]}),
        "pipeline": pipeline_version(cfg),
        "simulator": simulator_version(),
        "objective": stable_hash(cfg["objective"]),
    }
