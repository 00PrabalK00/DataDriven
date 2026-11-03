"""Inflation health of every form-found free-form shape: flutter, slack lines, flipped triangles, span collapse.
A canopy with large flutter or collapse has no steady inflated shape, so its steady CFD result is not meaningful.
  python scripts/v3/shape_health.py   (run from python/ with the venv; prints one CSV row per design)
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
D = json.load(open(ROOT / "results/freeform/designs_all.json"))
names = {tuple(np.round(d["free"], 9)): d["name"] for d in D if "free" in d}
print("name,flutter_mm,slack_lines,flipped_frac,proj_cm2,span_cm,min_line_N,converged")
for f in sorted(glob.glob(str(ROOT / "results/cfd/shapes/*.npz"))):
    z = np.load(f, allow_pickle=False)
    info = json.loads(str(z["info"]))
    w = info.get("design", {}).get("free")
    if w is None:
        continue
    X, T = z["X"], z["tris"]
    a, b, c = (X[T[:, k], :2] for k in range(3))
    s = 0.5 * ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
    n = names.get(tuple(np.round(w, 9)), "?")
    print(f"{n},{info.get('flutter_amp_m', 0) * 1e3:.1f},{info.get('slack_lines')},{(s < 0).mean():.3f},{s.sum() * 1e4:.1f},"
          f"{np.ptp(X[:, :2], axis=0).max() * 100:.1f},{min(info['line_tension_N']):.3f},{info.get('converged')}")
