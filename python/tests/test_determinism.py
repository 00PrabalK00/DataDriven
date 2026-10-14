import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest

from chutesim.geometry import Design
from chutesim.run_drop import write_drop


@pytest.mark.slow
def test_regeneration_pinned_env(cfg, tmp_path):
    """Same seed + config + pinned environment:
    - IMU log, LED log, timestamps, calibration and raw depth frames are bit-identical;
    - RGB frames are identical up to GPU rasterization nondeterminism (observed: a few pixels by
      a few grey levels, amplified by JPEG re-encoding), so they are compared with a tolerance, and the
      pipeline metrics computed from both bundles must agree."""
    a = Path(write_drop(Design(3, 0.1, 0.4), 4242, cfg, tmp_path / "a", "t")["obs"])
    b = Path(write_drop(Design(3, 0.1, 0.4), 4242, cfg, tmp_path / "b", "t")["obs"])
    files = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file() and p.name != "meta.json")
    assert files == sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file() and p.name != "meta.json")
    for rel in files:
        if rel.suffix == ".jpg":
            x = cv2.imread(str(a / rel)).astype(int)
            y = cv2.imread(str(b / rel)).astype(int)
            d = np.abs(x - y)
            assert d.max() <= 8 and (d.max(axis=2) > 0).mean() < 0.01, rel
        else:
            assert (a / rel).read_bytes() == (b / rel).read_bytes(), rel
    from pipeline.worker import process
    ma = process(str(a), str(tmp_path / "ea"), cfg["pipeline"])["modes"]["fused"]["preimpact_vz"]
    mb = process(str(b), str(tmp_path / "eb"), cfg["pipeline"])["modes"]["fused"]["preimpact_vz"]
    assert ma["status"] == mb["status"]
    if ma["value"] is not None:
        assert abs(ma["value"] - mb["value"]) < 0.01
