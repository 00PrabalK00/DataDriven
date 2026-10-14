import numpy as np

from chutesim.geometry import Design
from chutesim.physics import simulate_physics
from chutesim.scenario import sample_scenario
from chutesim.sensors import imu_observations


def test_imu_clips_at_range(cfg):
    sc = sample_scenario(1000, cfg)
    r = simulate_physics(Design(4, 0.15, 0.45), sc, cfg)
    assert np.abs(r["acc"]).max() > cfg["imu"]["accel_range_mps2"]   # true impact exceeds +-8 g
    imu = imu_observations(r, sc, cfg)
    lim = cfg["imu"]["accel_range_mps2"]
    assert np.abs(imu["acc"]).max() <= lim + cfg["imu"]["accel_lsb"]
    assert np.any(np.abs(imu["acc"]) >= lim - cfg["imu"]["accel_lsb"])  # saturated samples present


def test_imu_rate_dropouts_and_clock(cfg):
    sc = sample_scenario(1001, cfg)
    r = simulate_physics(Design(2, 0, 0.45), sc, cfg)
    imu = imu_observations(r, sc, cfg)
    dt = np.diff(imu["t_mcu"])
    assert abs(np.median(dt) - 1 / cfg["imu"]["rate_hz"]) < 1e-4
    assert imu["t_mcu"][0] > sc["mcu_offset"]


def test_depth_stereo_shadow_and_noise(cfg):
    from chutesim.camera import RealSenseSim
    dc = cfg["camera"]["depth"]
    h, w = dc["height"], dc["width"]
    zl = np.full((h, w), 3.0, np.float32)
    zl[:, 400:500] = 1.0                       # near object in front of a far wall
    shift = int(round(dc["fx"] * dc["baseline_m"] / 1.0))
    zr = np.full((h, w), 3.0, np.float32)
    zr[:, 400 - shift:500 - shift] = 1.0
    cam = RealSenseSim.__new__(RealSenseSim)
    cam.cfg = cfg
    cam._u = np.broadcast_to(np.arange(w, dtype=np.float32)[None, :], (h, w))
    out = cam.depth_imperfections(zl, zr, np.random.default_rng(0))
    # wall pixels just LEFT of the near object are hidden from the right imager -> invalid band
    # (left-imager-referenced depth, right imager at +baseline, as on a RealSense)
    shadow = out[:, 388:398]
    assert (out[:, 500:510] > 0).mean() > 0.95
    assert (shadow == 0).mean() > 0.8
    assert (out[:, 600:700] > 0).mean() > 0.95
    near = out[:, 420:480][out[:, 420:480] > 0] / 1000
    assert abs(near.mean() - 1.0) < 0.005
