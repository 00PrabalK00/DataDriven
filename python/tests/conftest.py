import os
import shutil

import pytest

os.environ.setdefault("MUJOCO_GL", "egl")

from chutesim.config import load_config  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture(scope="session")
def drop(tmp_path_factory, cfg):
    """One fully rendered simulated drop + its estimation output (shared by slow tests)."""
    from chutesim.geometry import Design
    from chutesim.run_drop import write_drop
    from pipeline.worker import process
    root = tmp_path_factory.mktemp("run")
    r = write_drop(Design(4.0, 0.15, 0.45), 1000, cfg, root, "t0001")
    m = process(r["obs"], str(root / "est" / "t0001"), cfg["pipeline"])
    return {"root": root, "obs": r["obs"], "truth": r["truth"], "metrics": m, "phys": r["phys"]}
