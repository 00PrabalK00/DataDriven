"""Virtual BNO085-like IMU and MCU clock / LED model.

Input: true specific force and angular rate at the IMU site (site frame = sensor frame, including the
configured mounting rotation) at the physics rate. Output: what the microcontroller would log.
"""
from __future__ import annotations

import numpy as np


def mcu_time(t_sim, scenario):
    """MCU-relative time (since log start) for simulator time t_sim."""
    return np.asarray(t_sim) * (1 + scenario["mcu_drift_ppm"] * 1e-6)


def led_schedule(cfg) -> list:
    """Firmware blink code: the MCU toggles the LED with pseudo-random on/off durations (fixed seed,
    a rig constant) for the whole recording, and logs every toggle. Any visible stretch (in flight or
    after landing) then gives several edges for clock alignment."""
    lc = cfg["drop"]["led_code"]
    r = np.random.default_rng(lc["seed"])
    t, out = lc["start_s"], []
    while t < cfg["drop"]["duration_s"] + 1.0:
        on = r.uniform(lc["min_interval_s"], lc["max_interval_s"])
        off = r.uniform(lc["min_interval_s"], lc["max_interval_s"])
        out.append([float(t), float(t + on)])
        t += on + off
    return out


def led_on(t_sim, scenario, cfg) -> np.ndarray:
    tm = mcu_time(t_sim, scenario)
    on = np.zeros(np.shape(tm), bool)
    for a, b in led_schedule(cfg):
        on |= (tm >= a) & (tm < b)
    return on


def imu_observations(phys: dict, scenario: dict, cfg: dict) -> dict:
    ic = cfg["imu"]
    rng = np.random.default_rng(scenario["imu_seed"])
    t = phys["t"]
    dt = phys["dt"]
    T = t[-1]
    drift = 1 + scenario["mcu_drift_ppm"] * 1e-6
    n = int(np.floor(T * drift * ic["rate_hz"]))
    t_rel = np.arange(n) / ic["rate_hz"] + rng.normal(0, ic["jitter_sd_s"], n)
    t_rel = np.sort(t_rel)
    t_s = t_rel / drift
    win = ic["antialias_window_s"]
    keep = (t_s >= win) & (t_s <= T)
    t_rel, t_s = t_rel[keep], t_s[keep]
    n = len(t_s)

    def window_mean(x):
        cs = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(x, axis=0)])
        hi = np.clip(np.floor(t_s / dt).astype(int) + 1, 1, len(x))
        lo = np.clip(hi - max(int(round(win / dt)), 1), 0, len(x) - 1)
        return (cs[hi] - cs[lo]) / (hi - lo)[:, None]

    acc = window_mean(phys["acc"])
    gyr = window_mean(phys["gyro"])
    sdt = 1.0 / ic["rate_hz"]
    ba = rng.normal(0, ic["accel_bias_sd"], 3) + np.cumsum(rng.normal(0, ic["accel_rw_sd"] * np.sqrt(sdt), (n, 3)), axis=0)
    bg = rng.normal(0, ic["gyro_bias_sd"], 3) + np.cumsum(rng.normal(0, ic["gyro_rw_sd"] * np.sqrt(sdt), (n, 3)), axis=0)
    acc = acc + ba + rng.normal(0, ic["accel_noise_sd"], (n, 3))
    gyr = gyr + bg + rng.normal(0, ic["gyro_noise_sd"], (n, 3))
    acc = np.clip(acc, -ic["accel_range_mps2"], ic["accel_range_mps2"])
    gyr = np.clip(gyr, -ic["gyro_range_rps"], ic["gyro_range_rps"])
    acc = np.round(acc / ic["accel_lsb"]) * ic["accel_lsb"]
    gyr = np.round(gyr / ic["gyro_lsb"]) * ic["gyro_lsb"]
    keep = rng.uniform(size=n) >= ic["dropout_prob"]
    t_mcu = scenario["mcu_offset"] + t_rel
    led_events = []
    T_mcu = t_rel[-1] if len(t_rel) else 0.0
    for a, b in led_schedule(cfg):
        if a > T_mcu:
            break
        led_events.append((scenario["mcu_offset"] + a, 1))
        led_events.append((scenario["mcu_offset"] + b, 0))
    return {
        "t_mcu": t_mcu[keep], "acc": acc[keep], "gyro": gyr[keep],
        "led_events": np.array(led_events),
        "truth_t_sim": t_s[keep], "truth_bias_acc": ba[keep], "truth_bias_gyro": bg[keep],
    }
