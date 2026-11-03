"""Animation for the Nov 3 deck: how 9 weights, 61 bumps and a water level make a canopy (real field, real level search).
  python/.venv/bin/python scripts/v3/deck_sand.py <ffmpeg>
Writes presentation/midway_2026-11-03/media/sand.mp4 and sand_cover.png.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from chutesim.config import load_config  # noqa: E402
from chutesim.freeform import EXTENT, _material, centres_and_orbits, field  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LightSource  # noqa: E402

OUT = ROOT / "presentation/midway_2026-11-03/media"
BG, ORANGE, LIGHT, MUTED, LILAC = "#15091F", "#FF8A3D", "#E9DDF2", "#B3A7BE", "#B58BD6"
SAND, WATER, FLOOR = np.array([1.0, 0.56, 0.26]), np.array([0.13, 0.46, 0.66]), np.array([0.15, 0.09, 0.2])
W, H, FPS, STEP = 1280, 720, 20, 3
ZMIN = -1.0

cfg = load_config(None)
A0 = float(cfg["canopy"]["A0_m2"])
R_eq = math.sqrt(A0 / math.pi)
s_m, base = field([0.0] * 9, "D6", R_eq)
px = (s_m[1] - s_m[0]) ** 2
min_hole = float(cfg.get("freeform", {}).get("min_hole_m2", 3e-5)) / px
BUMPS = [field(list(np.eye(9)[k]), "D6", R_eq)[1] - base for k in range(9)]
s = s_m / R_eq
X, Y = np.meshgrid(s, s)
C, ORB = centres_and_orbits("D6")
GROUP = np.zeros(len(C), int)
for k, idx in enumerate(ORB):
    GROUP[idx] = k
D = {d["name"]: d for d in json.load(open(ROOT / "results/freeform/designs_all.json"))}
W1, W2 = np.array(D["free56"]["free"]), np.array(D["free07"]["free"])
RING = ["edge", "edge", "edge", "outer", "outer", "middle", "middle", "inner", "centre"]


def phi_of(w):
    return base + sum(wk * b for wk, b in zip(w, BUMPS))


def level(phi):
    """The water level with exactly A0 of plastic, the same search as build_free_geometry."""
    srt = np.sort(phi.ravel())[::-1]
    n0 = int(A0 / px)
    lo, hi = float(srt[min(int(1.6 * n0), len(srt) - 1)]), float(srt[max(int(0.8 * n0), 0)])
    for _ in range(14):
        t = 0.5 * (lo + hi)
        _, a = _material(phi, t, px, min_hole)
        lo, hi = (t, hi) if a > A0 else (lo, t)
    return 0.5 * (lo + hi)


ls = LightSource(azdeg=315, altdeg=42)
fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=BG)
ax3 = fig.add_axes([-0.03, 0.14, 0.64, 0.86], projection="3d", facecolor=BG)
axb = fig.add_axes([0.62, 0.53, 0.35, 0.40], facecolor=BG)
axm = fig.add_axes([0.66, 0.14, 0.27, 0.36], facecolor=BG)


def draw(w, t, caption, active=None, dots=False, cut=False, area=None):
    Z = np.maximum(phi_of(w), t if t is not None else ZMIN)[::STEP, ::STEP]
    x, y = X[::STEP, ::STEP], Y[::STEP, ::STEP]
    h = ls.hillshade(Z, dx=s[STEP] - s[0], dy=s[STEP] - s[0], vert_exag=0.8)[..., None]
    flat = np.isclose(Z, t if t is not None else ZMIN)[..., None]
    col = np.clip(SAND * (0.32 + 0.82 * h), 0, 1)
    col = np.where(flat, WATER if t is not None else FLOOR, col)
    ax3.cla()
    ax3.set_axis_off(); ax3.set_box_aspect((1, 1, 0.55))
    ax3.set_xlim(-EXTENT, EXTENT); ax3.set_ylim(-EXTENT, EXTENT); ax3.set_zlim(ZMIN, 2.0)
    ax3.view_init(elev=58, azim=-58)
    ax3.plot_surface(x, y, Z, facecolors=np.dstack([col, np.ones(Z.shape)]), rstride=1, cstride=1, shade=False, linewidth=0, antialiased=False)
    # the 9 variables
    axb.cla(); axb.set_facecolor(BG)
    axb.set_xlim(-2.75, 1.75); axb.set_ylim(9.0, -1.1); axb.axis("off")
    axb.plot([0, 0], [-0.5, 8.5], color=MUTED, lw=1)
    axb.text(0, -0.85, "the 9 variables", color="white", fontsize=15, ha="center", weight="bold")
    axb.text(-1.65, -0.85, "dig", color=MUTED, fontsize=12); axb.text(1.72, -0.85, "add", color=MUTED, fontsize=12, ha="right")
    for k, wk in enumerate(w):
        on = active == k
        axb.barh(k, wk, height=0.68, color=ORANGE if on else LILAC, alpha=1 if on or active is None else 0.55)
        axb.text(-2.72, k, f"{k + 1}  {RING[k]}", color="white" if on else MUTED, fontsize=11, va="center", weight="bold" if on else "normal")
    # top view
    axm.cla(); axm.set_facecolor(BG); axm.set_aspect("equal"); axm.axis("off")
    lim = 1.55
    axm.set_xlim(-lim, lim); axm.set_ylim(-lim, lim)
    if cut:
        m, a = _material(phi_of(w), t, px, min_hole)
        axm.imshow(np.where(m, 1.0, np.nan), extent=[-EXTENT, EXTENT, -EXTENT, EXTENT], origin="lower", cmap="Greys_r", vmin=0, vmax=1, alpha=0.92, interpolation="bilinear")
        axm.text(0, -1.5, f"plastic: {a * 1e4:.0f} cm²", color=ORANGE, fontsize=15, ha="center", weight="bold")
    else:
        b = phi_of(w) - base
        axm.imshow(b, extent=[-EXTENT, EXTENT, -EXTENT, EXTENT], origin="lower", cmap="PuOr", vmin=-1.6, vmax=1.6, interpolation="bilinear")
    if dots:
        act = GROUP == active if active is not None else np.ones(len(C), bool)
        axm.scatter(C[~act, 0], C[~act, 1], s=9, c=MUTED)
        axm.scatter(C[act, 0], C[act, 1], s=26, c=ORANGE, edgecolors="white", linewidths=0.4)
    for t_ in fig.texts[:]:
        t_.remove()
    fig.text(0.04, 0.045, caption, color="white", fontsize=25, weight="bold", family="serif")
    fig.canvas.draw()
    return np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy()


def ease(a):
    return a * a * (3 - 2 * a)


def frames():
    zero = np.zeros(9)
    for _ in range(40):
        yield draw(zero, None, "Start with a smooth hill of sand")
    for _ in range(40):
        yield draw(zero, None, "Mark 61 spots. Symmetry groups them into 9", dots=True)
    cur = zero.copy()
    for k in range(9):
        start = cur[k]
        for j in range(10):
            cur[k] = start + (W1[k] - start) * ease((j + 1) / 10)
            yield draw(cur, None, "Each variable adds or digs one group of bumps", active=k, dots=True)
    t1 = level(phi_of(W1))
    t0 = max(ZMIN + 0.02, t1 - 0.8)  # low water: far more than 250 cm² sticks out
    for j in range(70):
        t = t0 + (t1 - t0) * ease(min(1.0, (j + 1) / 58))
        yield draw(W1, t, "Raise the water until exactly 250 cm² sticks out", cut=True)
    for _ in range(40):
        yield draw(W1, t1, "Above the water is plastic. The rest is cut away", cut=True)
    for j in range(60):
        w = W1 + (W2 - W1) * ease((j + 1) / 60)
        yield draw(w, level(phi_of(w)), "New numbers, new shape, still 250 cm²", cut=True)
    t2 = level(phi_of(W2))
    for _ in range(20):
        yield draw(W2, t2, "New numbers, new shape, still 250 cm²", cut=True)


enc = subprocess.Popen([sys.argv[1], "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", str(OUT / "sand.mp4")], stdin=subprocess.PIPE)
for n, f in enumerate(frames()):
    enc.stdin.write(f.tobytes())
    if n in (185, 200, 290):
        plt.imsave(OUT / f"_sand_{n}.png", f)
    if n == 245:
        plt.imsave(OUT / "sand_cover.png", f)
    if n % 60 == 0:
        print(n, flush=True)
enc.stdin.close()
enc.wait()
print("done", n + 1)
