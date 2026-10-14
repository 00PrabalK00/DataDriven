"""Clock alignment between the microcontroller (IMU, LED log) and the camera host clock using LED
flashes seen in the RGB stream: t_host = a * t_mcu + b."""
from __future__ import annotations

import numpy as np


def camera_edges(led: np.ndarray) -> np.ndarray:
    """led: (F,2) [t_host, state]. Edge time = midpoint between the frames that bracket the change."""
    if len(led) < 2:
        return np.zeros((0, 2))
    s = led[:, 1] > 0.5
    idx = np.nonzero(s[1:] != s[:-1])[0]
    return np.column_stack([(led[idx, 0] + led[idx + 1, 0]) / 2, s[idx + 1].astype(float)])


def solve_sync(led_cam: np.ndarray, led_mcu: np.ndarray, fps: float, min_edges: int = 3) -> dict:
    ce = camera_edges(led_cam)
    if len(ce) < min_edges or len(led_mcu) == 0:
        return {"status": "invalid_sync", "reason": f"camera LED edges={len(ce)} (<{min_edges})"}
    tol = 0.75 / fps
    best = None
    scored = []
    for tc, pc in ce:
        for tm, pm in led_mcu:
            if pc != pm:
                continue
            b = tc - tm
            res = []
            for tc2, pc2 in ce:
                cand = led_mcu[led_mcu[:, 1] == pc2, 0] + b
                res.append(np.min(np.abs(cand - tc2)) if len(cand) else np.inf)
            res = np.array(res)
            n_ok = int(np.sum(res < tol))
            score = (n_ok, -float(np.sum(np.minimum(res, tol) ** 2)))
            scored.append((score, b))
            if best is None or score > best[0]:
                best = (score, b)
    b = best[1]
    # ambiguity guard: an offset clearly different from the best must not match as many edges
    rival = max((sc[0] for sc, bb in scored if abs(bb - b) > 2 * tol), default=0)
    if rival >= best[0][0]:
        return {"status": "invalid_sync", "reason": f"ambiguous LED alignment ({best[0][0]} vs {rival} edges)"}
    pairs = []
    for tc2, pc2 in ce:
        cand = led_mcu[led_mcu[:, 1] == pc2, 0]
        k = int(np.argmin(np.abs(cand + b - tc2)))
        if abs(cand[k] + b - tc2) < tol:
            pairs.append((cand[k], tc2))
    pairs = np.array(pairs)
    if len(pairs) < min_edges:
        return {"status": "invalid_sync", "reason": f"matched LED edges={len(pairs)} (<{min_edges})"}
    # drift (~30 ppm) is negligible over a few seconds; an affine fit over a short span only adds
    # slope noise that the intercept extrapolates, so fit the rate only for long spans
    if np.ptp(pairs[:, 0]) >= 20.0:
        A = np.column_stack([pairs[:, 0], np.ones(len(pairs))])
        a, b = np.linalg.lstsq(A, pairs[:, 1], rcond=None)[0]
    else:
        a, b = 1.0, float(np.mean(pairs[:, 1] - pairs[:, 0]))
    res = pairs[:, 1] - (a * pairs[:, 0] + b)
    rms = float(np.sqrt(np.mean(res**2)))
    if rms > 0.6 / fps:
        return {"status": "invalid_sync", "reason": f"LED residual rms {rms:.4f}s"}
    return {"status": "ok", "a": float(a), "b": float(b), "n_edges": int(len(pairs)), "rms_s": rms}
