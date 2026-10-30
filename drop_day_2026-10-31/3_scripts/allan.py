# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "matplotlib"]
# ///
"""Allan-variance calibration of the payload IMU (BNO085) from a static log (scripts/imu_record.py --allan).

  uv run scripts/allan.py data/real/allan/<date>/imu.csv --out results/imu_allan
  uv run scripts/allan.py --selftest            # recover known noise parameters from synthetic data

Per axis: overlapping Allan deviation on log-spaced cluster times, then a non-negative least-squares fit
of the standard three-term model
    sigma^2(tau) = N^2 / tau  +  (0.664 B)^2  +  K^2 tau / 3
N = white noise (velocity/angle random walk density), B = bias instability, K = rate random walk.
Mapping to the simulator's IMU model (config/defaults.json "imu", chutesim/sensors.py):
    *_noise_sd (per-sample white noise at rate fs) = N * sqrt(fs)
    *_rw_sd    (bias random-walk density)          = K
    bias instability B has no term in the simulator yet (reported, not mapped)
    *_bias_sd  (turn-on bias spread) cannot come from one log (needs several power cycles)
Outputs: allan.json (per-axis N, B, K, suggested config values), allan.png. Evidence: L3 input (measured).
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import nnls

BI = 0.664  # sqrt(2 ln2 / pi): flat-floor factor of bias instability


def adev(x, fs, n_tau=60):
    """Overlapping Allan deviation of a rate signal x sampled at fs."""
    n = len(x)
    theta = np.concatenate([[0.0], np.cumsum(x)]) / fs
    m = np.unique(np.logspace(0, np.log10((n - 1) // 3), n_tau).astype(int))
    tau = m / fs
    out = np.empty(len(m))
    for i, mm in enumerate(m):
        d = theta[2 * mm:] - 2 * theta[mm:-mm] + theta[:-2 * mm]
        out[i] = np.sqrt(np.sum(d * d) / (2 * tau[i] ** 2 * (n - 2 * mm)))
    return tau, out


def fit(tau, sig):
    """NNLS fit of sigma^2 = a/tau + b + c*tau with relative weighting; returns N, B, K."""
    A = np.column_stack([1 / tau, np.ones_like(tau), tau / 3]) / (sig ** 2)[:, None]
    coef, _ = nnls(A, np.ones_like(tau))
    a, b, c = coef
    return float(np.sqrt(a)), float(np.sqrt(b) / BI), float(np.sqrt(c))


def analyse(t, acc, gyr):
    dt = np.diff(t)
    fs = 1.0 / np.median(dt)
    res = {"fs_hz": fs, "duration_h": float((t[-1] - t[0]) / 3600), "n": int(len(t)),
           "gaps_gt_3dt": int(np.sum(dt > 3 / fs)), "axes": {}}
    curves = {}
    for name, data in (("accel", acc), ("gyro", gyr)):
        for k, ax in enumerate("xyz"):
            tau, s = adev(data[:, k], fs)
            N, B, K = fit(tau, s)
            res["axes"][f"{name}_{ax}"] = {"N": N, "B": B, "K": K}
            curves[f"{name}_{ax}"] = (tau, s, N, B, K)
    for name in ("accel", "gyro"):
        Ns = [res["axes"][f"{name}_{a}"]["N"] for a in "xyz"]
        Ks = [res["axes"][f"{name}_{a}"]["K"] for a in "xyz"]
        Bs = [res["axes"][f"{name}_{a}"]["B"] for a in "xyz"]
        res[name] = {"N_mean": float(np.mean(Ns)), "B_mean": float(np.mean(Bs)), "K_mean": float(np.mean(Ks)),
                     "suggest_noise_sd_per_sample_at_200Hz": float(np.mean(Ns) * np.sqrt(200.0)),
                     "suggest_rw_sd": float(np.mean(Ks))}
    res["suggested_config_imu"] = {
        "accel_noise_sd": res["accel"]["suggest_noise_sd_per_sample_at_200Hz"],
        "accel_rw_sd": res["accel"]["suggest_rw_sd"],
        "gyro_noise_sd": res["gyro"]["suggest_noise_sd_per_sample_at_200Hz"],
        "gyro_rw_sd": res["gyro"]["suggest_rw_sd"],
        "note": "per-sample sd assumes the logger rate of 200 Hz; bias instability B not modelled; "
                "turn-on *_bias_sd needs several power cycles",
    }
    return res, curves


def plot(curves, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.8))
    for a, name, unit in ((axs[0], "accel", "m/s²"), (axs[1], "gyro", "rad/s")):
        for ax, col in zip("xyz", ("#c62828", "#2e7d32", "#1565c0")):
            tau, s, N, B, K = curves[f"{name}_{ax}"]
            a.loglog(tau, s, color=col, lw=1.6, label=f"{ax}: N={N:.2e} B={B:.2e} K={K:.2e}")
            a.loglog(tau, np.sqrt(N ** 2 / tau + (BI * B) ** 2 + K ** 2 * tau / 3), color=col, ls="--", lw=0.9)
        a.set_xlabel("cluster time τ [s]"); a.set_ylabel(f"Allan deviation [{unit}]")
        a.set_title(name); a.grid(True, which="both", alpha=0.3); a.legend(fontsize=8)
    fig.suptitle(title, fontsize=10); fig.tight_layout(); fig.savefig(path, dpi=130)


def selftest():
    """Synthetic static IMU with known white noise + random walk (+ quantisation like the BNO085 output);
    the fit must recover N and K within 10%."""
    rng = np.random.default_rng(1)
    fs, hours = 200.0, 2.0
    n = int(fs * 3600 * hours)
    t = np.arange(n) / fs
    true = {"accel": (0.03, 0.002), "gyro": (0.003, 0.0002)}   # (per-sample white sd, rw density): sim defaults
    data = {}
    for name, (wsd, rw) in true.items():
        bias = np.cumsum(rng.normal(0, rw / np.sqrt(fs), (n, 3)), axis=0)
        data[name] = bias + rng.normal(0, wsd, (n, 3))
    res, curves = analyse(t, data["accel"], data["gyro"])
    ok = True
    for name, (wsd, rw) in true.items():
        N_est, K_est = res[name]["N_mean"], res[name]["K_mean"]
        N_true = wsd / np.sqrt(fs)
        eN, eK = N_est / N_true - 1, K_est / rw - 1
        print(f"{name}: N est {N_est:.3e} true {N_true:.3e} ({eN:+.1%}) | K est {K_est:.3e} true {rw:.3e} ({eK:+.1%})")
        ok &= abs(eN) < 0.10 and abs(eK) < 0.10
    print("SELFTEST", "PASS" if ok else "FAIL")
    return ok, res, curves


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("imu_csv", nargs="?")
    ap.add_argument("--out", default="results/imu_allan")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.selftest:
        ok, res, curves = selftest()
        plot(curves, out / "allan_selftest.png", "Allan self-test on synthetic data (dashed = fit)")
        (out / "allan_selftest.json").write_text(json.dumps(res, indent=1))
        raise SystemExit(0 if ok else 1)
    d = np.loadtxt(a.imu_csv, delimiter=",", skiprows=1)
    t, acc, gyr = d[:, 0], d[:, 1:4], d[:, 4:7]
    res, curves = analyse(t, acc, gyr)
    res["source"] = str(a.imu_csv)
    (out / "allan.json").write_text(json.dumps(res, indent=1))
    plot(curves, out / "allan.png", f"BNO085 Allan deviation ({res['duration_h']:.1f} h static, {res['fs_hz']:.0f} Hz; dashed = fit)")
    print(json.dumps(res["suggested_config_imu"], indent=1))
    print(f"gaps > 3 samples: {res['gaps_gt_3dt']}; wrote {out}/allan.json, allan.png")


if __name__ == "__main__":
    main()
