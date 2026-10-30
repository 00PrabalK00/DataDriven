"""Falling-pattern analysis from the estimated trajectories (works for simulated and real drops alike).

Inputs are the shared pipeline's outputs est/<trial>/traj_{imu,fused}.npz (t, p, v, R) + metrics.json; for
simulated drops the truth folder can be overlaid to show reconstruction accuracy. Everything is aligned to the
detected impact (t = 0). Pattern features:
  tilt angle (body z vs vertical), swing amplitude and dominant swing frequency (tilt spectrum in flight),
  spin rate (yaw rate about the vertical), lateral drift, descent-speed profile.

  python -m ddd.flightviz <run_root> <trial> [<trial> ...] --out results/flight_patterns [--truth]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _load(run_root: Path, trial: str, mode: str):
    z = np.load(run_root / "est" / trial / f"traj_{mode}.npz", allow_pickle=True)
    m = json.load(open(run_root / "est" / trial / "metrics.json"))
    return {k: z[k] for k in z.files}, m


def _impact_time(m: dict, mode: str, t: np.ndarray, v: np.ndarray) -> float:
    c = m["modes"].get(mode, {}).get("contact_t")
    if c is not None:
        return float(c)
    return float(t[int(np.argmax(np.abs(np.gradient(v[:, 2], t))))])  # fallback: largest vertical jerk


def features(traj: dict, t_impact: float, release_window: float = 2.0) -> dict:
    t = traj["t"] - t_impact
    fly = (t > -release_window) & (t < -0.02)
    R = traj["R"]
    tilt = np.degrees(np.arccos(np.clip(R[:, 2, 2], -1, 1)))           # body z vs world z
    yaw = np.unwrap(np.arctan2(R[:, 1, 0], R[:, 0, 0]))
    spin = np.gradient(yaw, traj["t"])
    out = {"t": t, "tilt_deg": tilt, "spin_rad_s": spin, "p": traj["p"], "v": traj["v"]}
    if fly.sum() > 16:
        tf = tilt[fly] - tilt[fly].mean()
        dt = np.median(np.diff(traj["t"][fly]))
        f = np.fft.rfftfreq(len(tf), dt)
        P = np.abs(np.fft.rfft(tf * np.hanning(len(tf)))) ** 2
        band = (f > 0.3) & (f < 8)
        out["swing_freq_hz"] = float(f[band][np.argmax(P[band])]) if band.any() else float("nan")
        out["swing_amp_deg"] = float(0.5 * (np.percentile(tilt[fly], 95) - np.percentile(tilt[fly], 5)))
        out["tilt_rms_deg"] = float(np.sqrt(np.mean(tilt[fly] ** 2)))
        out["spin_mean_rad_s"] = float(np.mean(spin[fly]))
        out["lateral_drift_m"] = float(np.hypot(*(traj["p"][fly][-1, :2] - traj["p"][fly][0, :2])))
        out["descent_speed_end"] = float(-traj["v"][fly][-1, 2])
    return out


def classify(f: dict) -> str:
    """Simple rule-based label (the k-means clustering in ddd.flight is the data-driven version)."""
    if not np.isfinite(f.get("tilt_rms_deg", np.nan)):
        return "unknown"
    if f["tilt_rms_deg"] > 25:
        return "tumbling"
    if f["swing_amp_deg"] > 8:
        return "swinging"
    if f["lateral_drift_m"] > 0.5:
        return "drifting"
    return "stable"


def plot_drop(run_root: Path, trial: str, out_dir: Path, truth: bool = False) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    res = {}
    fig = plt.figure(figsize=(15, 8.5))
    ax3 = fig.add_subplot(2, 3, (1, 4))
    axs = [fig.add_subplot(2, 3, i) for i in (2, 3, 5, 6)]
    col = {"imu": "#1565c0", "fused": "#c62828", "truth": "#2e7d32"}
    for mode in ("imu", "fused"):
        try:
            tr, m = _load(run_root, trial, mode)
        except FileNotFoundError:
            continue
        ti = _impact_time(m, mode, tr["t"], tr["v"])
        f = features(tr, ti)
        res[mode] = {k: v for k, v in f.items() if np.isscalar(v)}
        res[mode]["pattern"] = classify(f)
        sel = f["t"] < 0.0
        p = f["p"][sel] - f["p"][sel][-1]
        lab = f"{mode.upper()} estimate"
        fl = f["t"][sel] > -1.05
        ax3.plot(100 * p[fl, 0], 100 * p[fl, 1], color=col[mode], lw=2, label=lab)
        axs[0].plot(f["t"][sel], -f["v"][sel, 2], color=col[mode], label=lab)
        axs[1].plot(f["t"][sel], f["tilt_deg"][sel], color=col[mode], label=lab)
        axs[2].plot(f["t"][sel], f["spin_rad_s"][sel], color=col[mode], label=lab)
        axs[3].plot(f["t"][sel], np.hypot(f["v"][sel, 0], f["v"][sel, 1]), color=col[mode], label=lab)
    if truth and (run_root / "truth" / trial / "truth.npz").exists():
        z = np.load(run_root / "truth" / trial / "truth.npz")
        tj = json.load(open(run_root / "truth" / trial / "truth.json"))
        t = z["t"] - tj["contact_t_sim"]
        sel = (t > -2.0) & (t < 0.0)
        p = z["qpos"][sel, :3]
        p = p - p[-1]
        fl = t[sel] > -1.05
        ax3.plot(100 * p[fl, 0], 100 * p[fl, 1], color=col["truth"], lw=1.5, ls="--", label="simulator truth")
        axs[0].plot(t[sel], -z["v_box"][sel, 2], color=col["truth"], ls="--", label="truth")
        axs[3].plot(t[sel], np.hypot(z["v_box"][sel, 0], z["v_box"][sel, 1]), color=col["truth"], ls="--", label="truth")
    ax3.set_xlabel("x [cm]"); ax3.set_ylabel("y [cm]"); ax3.set_aspect("equal", adjustable="datalim"); ax3.grid(alpha=0.3)
    ax3.plot(0, 0, "k*", ms=12, label="impact point")
    ax3.set_title("Top view: horizontal path from release to impact"); ax3.legend(fontsize=8)
    for a, (yl, tt) in zip(axs, [("descent speed [m/s]", "Descent speed"), ("tilt [deg]", "Tilt / swing"),
                                  ("yaw rate [rad/s]", "Spin about vertical"), ("lateral speed [m/s]", "Lateral drift speed")]):
        a.set_xlabel("time to impact [s]"); a.set_ylabel(yl); a.set_title(tt); a.grid(alpha=0.3); a.set_xlim(-2.0, 0.05)
    axs[0].legend(fontsize=8)
    pat = res.get("fused", res.get("imu", {}))
    fig.suptitle(f"Falling pattern, drop {trial}: {pat.get('pattern', '?')} | swing {pat.get('swing_amp_deg', float('nan')):.1f} deg "
                 f"at {pat.get('swing_freq_hz', float('nan')):.2f} Hz | drift {pat.get('lateral_drift_m', float('nan')):.2f} m",
                 fontsize=12, weight="bold")
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / f"flight_pattern_{trial}.png", dpi=140)
    plt.close(fig)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_root")
    ap.add_argument("trials", nargs="+")
    ap.add_argument("--out", default="results/flight_patterns")
    ap.add_argument("--truth", action="store_true")
    a = ap.parse_args()
    allres = {t: plot_drop(Path(a.run_root), t, Path(a.out), a.truth) for t in a.trials}
    (Path(a.out) / "patterns.json").write_text(json.dumps(allres, indent=1, default=float))
    for t, r in allres.items():
        f = r.get("fused", r.get("imu", {}))
        print(t, f.get("pattern"), {k: round(v, 3) for k, v in f.items() if isinstance(v, float)})


if __name__ == "__main__":
    main()
