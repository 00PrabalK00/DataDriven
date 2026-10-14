import json
import shutil
import subprocess
import sys

import numpy as np
import pytest

from pipeline.bundle import TruthAccessError, guard_path, load_bundle


def test_rgb_depth_timestamps_distinct(drop, cfg):
    b = load_bundle(drop["obs"])
    common = np.intersect1d(b.rgb_times[:, 0], b.depth_times[:, 0])
    tr = dict(b.rgb_times)
    td = dict(b.depth_times)
    d = np.array([td[k] - tr[k] for k in common])
    assert np.all(np.abs(d) > 1e-4)
    n_nom = cfg["drop"]["duration_s"] * cfg["camera"]["color"]["fps"]
    assert 0.95 * n_nom < len(b.rgb_times) <= n_nom and 0.95 * n_nom < len(b.depth_times) <= n_nom


def test_worker_refuses_truth(drop):
    with pytest.raises(TruthAccessError):
        guard_path(drop["truth"])
    with pytest.raises(TruthAccessError):
        load_bundle(drop["truth"])


def test_worker_process_has_no_truth_path(drop):
    from chutesim import evaluate as E
    env = E._scrubbed_env()
    truth_root = str(drop["root"] / "truth")
    assert not any(truth_root in v for v in env.values())
    w = E._worker()
    try:
        with open(f"/proc/{w.pid}/cmdline", "rb") as f:
            argv = f.read().decode()
        with open(f"/proc/{w.pid}/environ", "rb") as f:
            envs = f.read().decode()
        assert "truth" not in argv and truth_root not in envs
    finally:
        w.stdin.close()
        w.wait(timeout=30)
        E._WORKER = None


def test_audit_hook_no_truth_open(drop, cfg, tmp_path):
    """Run the estimation in a fresh interpreter with an audit hook that fails on any open() under
    the truth root (the hook path is given to the test harness, not to the worker)."""
    truth_root = str(drop["root"] / "truth")
    code = f"""
import sys, json
TR = {truth_root!r}
def hook(ev, args):
    if ev == 'open' and args and isinstance(args[0], str) and args[0].startswith(TR):
        raise RuntimeError('TRUTH OPENED: ' + args[0])
sys.addaudithook(hook)
from pipeline.worker import process
process({drop['obs']!r}, {str(tmp_path / 'est')!r}, json.loads({json.dumps(json.dumps(cfg['pipeline']))}))
print('OK')
"""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=1200)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr[-2000:]


def test_metrics_identical_without_truth(drop, cfg, tmp_path):
    from pipeline.worker import process
    moved = tmp_path / "truth_moved"
    shutil.move(str(drop["root"] / "truth"), str(moved))
    try:
        m = process(drop["obs"], str(tmp_path / "est2"), cfg["pipeline"])
    finally:
        shutil.move(str(moved), str(drop["root"] / "truth"))
    a = json.dumps(m["modes"], sort_keys=True)
    b = json.dumps(drop["metrics"]["modes"], sort_keys=True)
    assert a == b


def test_estimates_against_truth(drop):
    """Separate validation process compares estimates with truth (thresholds per mode)."""
    from validation.compare import compare
    c = compare(drop["root"], "t0001")
    f = c["modes"]["fused"]
    assert f["preimpact_vz_status"] == "ok"
    assert abs(f["preimpact_vz_err"]) < 0.15
    assert max(f["pos_rmse_flight_m"]) < 0.03
    assert abs(f["contact_t_err_s"]) < 0.01
    i = c["modes"]["imu"]
    assert abs(i["preimpact_vz_err"]) < 0.15
    cam = c["modes"]["camera"]
    assert cam["preimpact_vz_status"] == "ok" and abs(cam["preimpact_vz_err"]) < 0.5
    assert abs(c["sync_offset_err_s"]) < 0.01


def test_contact_and_decel_from_observations_only(drop):
    m = drop["metrics"]["modes"]["fused"]
    assert m["contact_t"] is not None and m["decel"]["status"] == "ok"
    assert m["decel"]["value"] in ("yes", "no")


def test_tracking_loss_gives_invalid_not_zero(drop, cfg, tmp_path):
    """Remove all RGB frames near impact: speed must be missing with a status, never 0."""
    from pipeline.worker import process
    obs2 = tmp_path / "obs_cut"
    shutil.copytree(drop["obs"], obs2)
    b = load_bundle(obs2)
    tc = drop["metrics"]["modes"]["fused"]["contact_t"]
    for k, t in b.rgb_times:
        if tc - 0.6 < t < tc + 0.05:
            (obs2 / "rgb" / f"{int(k):06d}.jpg").unlink()
    m = process(str(obs2), str(tmp_path / "est_cut"), cfg["pipeline"])
    f = m["modes"]["fused"]["preimpact_vz"]
    assert f["value"] is None and f["status"].startswith("invalid")


def test_contact_failure_invalid(drop, cfg, tmp_path):
    """No impact in the IMU log (truncated before landing) -> invalid_contact, never a number."""
    from pipeline.worker import process
    obs2 = tmp_path / "obs_noimp"
    shutil.copytree(drop["obs"], obs2)
    imu = np.loadtxt(obs2 / "imu.csv", delimiter=",", skiprows=1)
    rel = drop["metrics"]["modes"]["imu"]["release_t"]
    imu = imu[imu[:, 0] < rel + 0.4]
    np.savetxt(obs2 / "imu.csv", imu, delimiter=",", header="t_mcu,ax,ay,az,gx,gy,gz", comments="", fmt="%.6f")
    m = process(str(obs2), str(tmp_path / "est_noimp"), cfg["pipeline"])
    assert m["modes"]["imu"]["preimpact_vz"]["value"] is None
    assert m["modes"]["imu"]["preimpact_vz"]["status"] == "invalid_contact"


def test_fallback_com_correction(drop, cfg):
    """Visible-surface centroid + COM correction reduces bias vs. the raw surface point; its
    covariance is inflated relative to PnP."""
    from pipeline.detect import Detector
    tz = np.load(drop["root"] / "truth" / "t0001" / "truth.npz")
    tj = json.load(open(drop["root"] / "truth" / "t0001" / "truth.json"))
    b = load_bundle(drop["obs"])
    d = Detector(b, cfg["pipeline"])
    errs_c, errs_s = [], []
    for k, t in b.rgb_times[-40:]:
        bgr = b.read_rgb(k)
        j = int(np.argmin(np.abs(b.depth_times[:, 1] - t)))
        fb = d.blob(bgr, b.read_depth(b.depth_times[j, 0]))
        if fb is None:
            continue
        i = int(round((t - tj["host_offset"]) / 0.001))
        pc = d.R_wc @ fb["p_cam"] + d.t_wc
        ray = fb["p_cam"] / np.linalg.norm(fb["p_cam"])
        ps = d.R_wc @ (fb["p_cam"] - ray * d.half[0]) + d.t_wc
        errs_c.append(np.linalg.norm(pc - tz["qpos"][i, :3]))
        errs_s.append(np.linalg.norm(ps - tz["qpos"][i, :3]))
    assert len(errs_c) > 10
    assert np.mean(errs_c) < np.mean(errs_s)
    ep = cfg["pipeline"]["ekf"]
    assert ep["pos_sd_fallback"] > ep["pos_sd_pnp_lateral"]
