"""MATLAB bridge. MATLAB runs this module in a persistent, separate Python process
(pyenv ExecutionMode="OutOfProcess") and exchanges JSON strings; every request/result is also
appended to an on-disk JSONL log by the Evaluator.

    py.chutesim.bridge.evaluate_json(jsonencode(req))
"""
from __future__ import annotations

import json
import os

from .aeromap import get_map
from .config import load_config
from .geometry import Design, build_geometry, rich_outline, outline_from_radial, geometry_features

_STATE = {"evaluator": None, "cfg": None, "cfg_key": None}


def _cfg(overrides_json: str | None = None):
    key = overrides_json or ""
    if _STATE["cfg"] is None or _STATE["cfg_key"] != key:
        _STATE["cfg"] = load_config(overrides=json.loads(overrides_json) if overrides_json else None)
        _STATE["cfg_key"] = key
        if _STATE["evaluator"] is not None:
            _STATE["evaluator"].close()
            _STATE["evaluator"] = None
    return _STATE["cfg"]


def config_json(overrides_json: str = "") -> str:
    return json.dumps(_cfg(overrides_json or None))


def evaluator(n_workers=None, log_path=None, overrides_json=""):
    from .evaluate import Evaluator
    cfg = _cfg(overrides_json or None)
    if _STATE["evaluator"] is None:
        _STATE["evaluator"] = Evaluator(cfg, n_workers=n_workers, log_path=log_path)
    return _STATE["evaluator"]


def evaluate_json(req_json: str) -> str:
    """req: {designs: [[q,l,r],...], seeds: [...], tag?, n_workers?, log_path?, keep_frames?, overrides?}"""
    req = json.loads(req_json)
    ev = evaluator(req.get("n_workers"), req.get("log_path"), json.dumps(req["overrides"]) if req.get("overrides") else "")
    if req.get("log_path"):
        from pathlib import Path
        ev.log_path = Path(req["log_path"])
    res = ev.evaluate([d if isinstance(d, dict) else tuple(d) for d in req["designs"]], [int(s) for s in req["seeds"]],
                      keep_frames=req.get("keep_frames"), tag=req.get("tag", "matlab"))
    slim = [{k: r[k] for k in ("design", "canonical", "feasible", "objective", "cache_hits", "simulated_drops",
                               "evidence_level")} for r in res]
    return json.dumps({"results": slim, "counters": ev.counters}, default=float)


def counters_json() -> str:
    ev = _STATE["evaluator"]
    return json.dumps(ev.counters if ev else {})


def reset_counters() -> str:
    ev = _STATE["evaluator"]
    if ev:
        for k in ev.counters:
            ev.counters[k] = 0
        ev._seen.clear()
    return "ok"


def geometry_json(q: float, slit_len: float, slit_r: float, overrides_json: str = "") -> str:
    cfg = _cfg(overrides_json or None)
    g = build_geometry(Design(float(q), float(slit_len), float(slit_r)), cfg)
    d = g.to_dict()
    d["features"] = geometry_features(g)
    d["rich_r64"] = rich_outline(g, 64).tolist()
    amap, ver = get_map(cfg)
    a = amap(g, cfg)
    d["aero"] = {k: v for k, v in a.items() if k != "features"}
    return json.dumps(d)


def radial_geometry_json(r_norm_json: str, overrides_json: str = "") -> str:
    """Geometry/feature summary for a rich r(theta) outline (representation studies)."""
    import numpy as np
    from .geometry import Geometry, polygon_area
    cfg = _cfg(overrides_json or None)
    r = np.asarray(json.loads(r_norm_json), float)
    A0 = cfg["canopy"]["A0_m2"]
    poly = outline_from_radial(r, A0)
    g = Geometry(Design(0, 0, 0), poly, np.zeros((0, 2, 2)), np.zeros(0), np.zeros((0, 2)), A0,
                 (A0 / np.pi) ** 0.5, 0.0, polygon_area(poly), 0.0)
    valid = bool(np.all(r > 0.2) and np.all(np.isfinite(r)))
    return json.dumps({"features": geometry_features(g), "valid": valid, "area": polygon_area(poly)})


def close() -> str:
    if _STATE["evaluator"] is not None:
        _STATE["evaluator"].close()
        _STATE["evaluator"] = None
    return "ok"


def vertical_drop_json(q: float, slit_len: float, slit_r: float, seed: int = 1000) -> str:
    """MuJoCo vertical-only drop (no tilt/wind/lateral forces) for parity checks against ode45."""
    import numpy as np
    from .physics import simulate_physics
    from .scenario import sample_scenario
    cfg = _cfg(None)
    sc = sample_scenario(int(seed), cfg)
    sc.update(dict(dh=0.0, dxy=[0, 0], wind=[0, 0], line_len_err=[0.0] * cfg["canopy"]["n_lines"], area_err=0.0,
                   rho_frac=0.0, deploy_u=1.0, slit_len_err_m=0.0, yaw=0.0))
    r = simulate_physics(Design(float(q), float(slit_len), float(slit_r)), sc, cfg, vertical_only=True)
    i = int(np.searchsorted(r["t"], r["contact_t"])) - 1
    from .payload import frontal_area
    zb = -cfg["payload"]["extent_min_m"][2]
    return json.dumps({"v_contact": float(-r["v_box"][i, 2]), "t_contact_after_release": float(r["contact_t"] - r["release_t"]),
                       "K_i": r["K_i"], "K_o": r["K_o"], "tau": r["aero_params"]["tau_s"], "rho": r["rho"],
                       "h0": float(r["qpos"][0, 2] - zb - cfg["contact"]["pad_size_m"][2]),
                       "m": cfg["payload"]["mass_kg"] + cfg["canopy"]["mass_kg"],
                       "K_box": cfg["payload"]["Cd_box"] * frontal_area(cfg["payload"]),
                       "g": cfg["physics"]["g"]})


def flight_features_json(cache_root: str = "", mode: str = "fused") -> str:
    """Per-drop sensor-derived flight features from the evaluation cache (for PCA / k-means /
    surrogate studies). Rows with any invalid feature are reported with nulls, never zeros."""
    from pathlib import Path
    from .evaluate import DEFAULT_CACHE
    root = Path(cache_root) if cache_root else DEFAULT_CACHE
    feats = ("preimpact_vz", "lateral_speed", "landing_offset", "tilt_rms_deg", "tilt_max_deg", "swing_rate_rms",
             "peak_specific_force_g")
    rows = []
    for p in root.rglob("*.json"):
        with open(p) as f:
            e = json.load(f)
        mm = e["metrics"]["modes"][mode]
        d = e["manifest"]["design"]
        if d.get("radial") is not None:      # free-form (latent-study) shapes are not in the 3-knob table
            continue
        rows.append({"q": d["q"], "slit_len": d["slit_len"], "slit_r": d["slit_r"], "seed": e["manifest"]["seed"],
                     **{k: mm[k]["value"] for k in feats},
                     "decel": mm["decel"]["value"], "clipped": mm["peak_specific_force_g"]["status"] == "clipped"})
    return json.dumps({"features": list(feats), "rows": rows})


def flight_features_csv(path: str, cache_root: str = "", mode: str = "fused") -> str:
    """Same as flight_features_json, written as CSV (missing values -> empty/NaN, never 0)."""
    import csv
    d = json.loads(flight_features_json(cache_root, mode))
    cols = ["q", "slit_len", "slit_r", "seed", *d["features"], "decel", "clipped"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in d["rows"]:
            w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])
    return json.dumps({"rows": len(d["rows"]), "path": path})
