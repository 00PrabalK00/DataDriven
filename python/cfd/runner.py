"""OpenFOAM command runner with two backends, selected by env CFD_BACKEND=docker|native.

docker: opencfd/openfoam-run:2406 (override with CFD_IMAGE), case dir mounted at /case.
native: OpenFOAM v2406 installed from the opencfd apt repo (scripts/v2/install_openfoam_native.sh),
        environment from /usr/lib/openfoam/openfoam2406/etc/bashrc (override with CFD_FOAM_BASHRC).
Default: docker if `docker info` works, else native. Both use the same OpenFOAM version (v2406).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

FOAM_VERSION = os.environ.get("CFD_FOAM_VERSION", "2406")
IMAGE = os.environ.get("CFD_IMAGE", f"opencfd/openfoam-run:{FOAM_VERSION}")
BASHRC = os.environ.get("CFD_FOAM_BASHRC", f"/usr/lib/openfoam/openfoam{FOAM_VERSION}/etc/bashrc")
DOCKER_BASHRC = f"/usr/lib/openfoam/openfoam{FOAM_VERSION}/etc/bashrc"


@lru_cache(maxsize=1)
def backend() -> str:
    b = os.environ.get("CFD_BACKEND", "").strip().lower()
    if b in ("docker", "native"):
        return b
    if shutil.which("docker"):
        try:
            if subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0:
                return "docker"
        except (subprocess.TimeoutExpired, OSError):
            pass
    return "native"


def run_script(case_dir: str | Path, script: str, log: str | Path, timeout: float | None = None) -> int:
    """Run a bash script inside the OpenFOAM environment with cwd = case dir; stdout+stderr -> log."""
    case_dir = Path(case_dir).resolve()
    env_lines = ("export OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 "
                 "OMPI_MCA_btl_vader_single_copy_mechanism=none OMPI_MCA_rmaps_base_oversubscribe=1\n")
    if backend() == "docker":
        body = f"source {DOCKER_BASHRC} >/dev/null 2>&1\n{env_lines}export HOME=/tmp\ncd /case\n{script}"
        cmd = ["docker", "run", "--rm", "--ipc=host", "-u", f"{os.getuid()}:{os.getgid()}",
               "-v", f"{case_dir}:/case", "--entrypoint", "", IMAGE, "bash", "-c", body]
    else:
        body = f"source {BASHRC} >/dev/null 2>&1\n{env_lines}cd '{case_dir}'\n{script}"
        cmd = ["bash", "-c", body]
    with open(log, "w") as f:
        p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=timeout)
    return p.returncode


def describe() -> dict:
    """Backend and image/install identification for result provenance."""
    return {"backend": backend(), "foam_version": f"v{FOAM_VERSION}",
            "image": IMAGE if backend() == "docker" else f"native:{BASHRC}"}
