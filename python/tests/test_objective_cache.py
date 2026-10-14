import copy

import pytest

from chutesim.evaluate import cache_key
from chutesim.geometry import Design
from chutesim.objective import geometry_infeasible, score, score_bounds


def _m(vz, lat=0.1, dec="yes", st="ok"):
    v = (lambda x: {"value": x, "status": "ok"})
    bad = {"value": None, "status": st, "reason": "test"}
    mm = {"preimpact_vz": v(vz) if st == "ok" else bad, "lateral_speed": v(lat) if st == "ok" else bad,
          "decel": v(dec) if st == "ok" else bad}
    return {"modes": {"fused": mm}}


def test_any_invalid_gives_marked_penalty_above_all_valid(cfg):
    b = score_bounds(cfg)
    worst_valid = score([_m(b["S_cap"] * 3, lat=99, dec="no")] * 5, cfg)
    assert worst_valid["status"] == "ok"
    one_bad = score([_m(1.0)] * 4 + [_m(None, st="invalid_tracking")], cfg)
    assert one_bad["status"] == "infeasible_sensing" and one_bad["penalty_marked"]
    assert one_bad["score"] > worst_valid["score"]
    assert one_bad["mean_preimpact_vz"] is None           # never a fabricated speed
    assert one_bad["sensing_failure_scenarios"] == 1 and one_bad["aero_failures"] == []
    assert geometry_infeasible([], cfg)["score"] == one_bad["score"]


def test_measured_speed_not_clipped_anomaly_logged(cfg):
    b = score_bounds(cfg)
    s = score([_m(b["S_cap"] + 2)] * 2, cfg)
    assert s["measured_preimpact_vz"] == [b["S_cap"] + 2] * 2
    assert s["mean_preimpact_vz"] == b["S_cap"] + 2
    assert len(s["anomalies"]) == 2
    assert s["score"] <= b["S_cap"] + cfg["objective"]["drift_weight"] * cfg["objective"]["drift_cap"] \
        + cfg["objective"]["decel_weight"] * cfg["objective"]["decel_cap"]


def test_aero_failures_counted_separately(cfg):
    s = score([_m(6.0, dec="no"), _m(6.0)], cfg)
    assert s["status"] == "ok" and len(s["aero_failures"]) == 1 and s["sensing_failures"] == []
    assert s["decel_penalty"] > 0


def test_cache_key_components(cfg):
    d = Design(4.0, 0.15, 0.45)
    k0, _ = cache_key(d, 1000, cfg, "prior-v1")
    assert cache_key(d, 1001, cfg, "prior-v1")[0] != k0
    assert cache_key(d, 1000, cfg, "fit-abc")[0] != k0
    assert cache_key(Design(4.0 + 1e-6, 0.15, 0.45), 1000, cfg, "prior-v1")[0] != k0   # FD perturbation
    assert cache_key(Design(4.0, 0.15 + 1e-6, 0.45), 1000, cfg, "prior-v1")[0] != k0
    for section, key, val in [("payload", "mass_kg", 0.2), ("imu", "accel_noise_sd", 0.05),
                              ("pipeline", "impact_fmag_g", 3.5), ("scenario", "height_sd_m", 0.03),
                              ("objective", "drift_limit_mps", 0.4)]:
        c = copy.deepcopy(cfg)
        c[section][key] = val
        assert cache_key(d, 1000, c, "prior-v1")[0] != k0, section
    # zero-slit designs share a key regardless of nominal slit position
    assert cache_key(Design(3, 0, 0.3), 1000, cfg, "prior-v1")[0] == cache_key(Design(3, 0, 0.6), 1000, cfg, "prior-v1")[0]
