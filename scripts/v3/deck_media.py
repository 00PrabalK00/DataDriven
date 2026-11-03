"""Animations and renders for the Nov 3 deck (presentation/midway_2026-11-03/media), dark background.
  python/.venv/bin/python scripts/v3/deck_media.py <ffmpeg> [inflate ga flow gallery]
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from cfd.batch import _design  # noqa: E402
from chutesim.config import load_config  # noqa: E402
from chutesim.cutouts import build_any_geometry  # noqa: E402
from chutesim.freeform import build_free_geometry, free_design  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

OUT = ROOT / "presentation/midway_2026-11-03/media"
BG, ORANGE, LIGHT, GREY = "#15091F", "#FF8A3D", "#E9DDF2", "#7E7488"
FFMPEG = sys.argv[1]
SHAPES = ROOT / "results/cfd/shapes"


def encoder(path, w, h, fps):
    return subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)


def grab(fig):
    fig.canvas.draw()
    return np.asarray(fig.canvas.buffer_rgba())[:, :, :3].tobytes()


def shape_file(test):
    for f in sorted(SHAPES.glob("*.npz")):
        z = np.load(f, allow_pickle=False)
        d = json.loads(str(z["info"])).get("design", {})
        if test(d):
            yield z


def canopy_axes(fig, rect, lim, elev, z0):
    ax = fig.add_axes(rect, projection="3d", facecolor=BG)
    ax.set_axis_off(); ax.set_box_aspect((1, 1, 1))
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(z0 - lim, z0 + lim)
    ax.view_init(elev=elev, azim=30)
    return ax


def draw_canopy(ax, P, T, color=(1.0, 0.54, 0.24)):
    tri = P[T]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    n[n[:, 2] < 0] *= -1
    light = np.array([0.45, -0.35, 0.82]); light /= np.linalg.norm(light)
    v = 0.28 + 0.72 * np.abs(n @ light)
    ax.add_collection3d(Poly3DCollection(tri, facecolors=np.c_[np.outer(v, color), np.ones(len(v))], edgecolors="none", linewidths=0, antialiased=False))


def inflate():
    z = next(shape_file(lambda d: d.get("cut") and d["cut"][0] == 0.12 and not d["cut"][1]))
    X, T, xy = z["X"], z["tris"], z["xy"]
    a, anch = z["attach"], z["anchors"]
    zr = X[:, 2].mean()
    flat = np.c_[xy - xy.mean(0), np.full(len(xy), zr)]
    X = X - np.r_[X[:, :2].mean(0), 0]
    anch = anch - np.r_[z["X"][:, :2].mean(0), 0]
    n, S, fps = 96, 760, 24
    enc = encoder(OUT / "inflate.mp4", S, S, fps)
    for i in range(n):
        s = np.clip((i - 14) / 44, 0, 1); s = s * s * (3 - 2 * s)
        P = (1 - s) * flat + s * X
        fig = plt.figure(figsize=(S / 100, S / 100), dpi=100, facecolor=BG)
        ax = canopy_axes(fig, [-.3, -.3, 1.6, 1.6], 0.125, 62 - 22 * s, zr - 0.035)
        ax.azim = 30 + i * 0.9
        draw_canopy(ax, P, T)
        for k, j in enumerate(a):
            ax.plot(*np.c_[P[j], anch[k]], color=LIGHT, lw=0.7, alpha=s)
        b = grab(fig); enc.stdin.write(b)
        if i == n - 1:
            fig.savefig(OUT / "inflate_final.png", facecolor=BG, dpi=200)
        plt.close(fig)
    enc.stdin.close(); enc.wait()


def ga():
    cfg = load_config(None)
    win = json.load(open(ROOT / "results/freeform/designs_win.json"))[0]["free"]
    runs = [json.load(open(f)) for f in sorted((ROOT / "results/freeform/final/bench/free_runs").glob("ga_*.json"))]
    r = min(runs, key=lambda q: np.linalg.norm(np.array(q["xbest"]) - np.array(win)))
    print("GA run", r["runIndex"], r["fbest"], np.linalg.norm(np.array(r["xbest"]) - np.array(win)))
    G = [build_free_geometry(free_design(tuple(x), "D6"), cfg) for x in r["X"]]
    F, st = np.array(r["F"]), r["status"]
    tr = np.minimum(np.array(r["bestTrace"]), 6.7)
    W, H, fps, hold = 1280, 720, 12, 10
    enc = encoder(OUT / "ga_evolve.mp4", W, H, fps)
    fr = []
    for g in range(10):
        fr += [g] * hold
    fr += [9] * 24
    for t, g in enumerate(fr):
        fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=BG)
        idx = range(g * 20, g * 20 + 20)
        okF = [F[i] if st[i] == "ok" else 99 for i in idx]
        top = g * 20 + int(np.argmin(okF))
        for k, i in enumerate(idx):
            ax = fig.add_axes([.015 + (k % 5) * .125, .77 - (k // 5) * .235, .115, .205], facecolor=BG)
            good = st[i] == "ok"
            c = ORANGE if i == top else ("#B58BD6" if good else "#3A3044")
            o = np.vstack([G[i].outline, G[i].outline[:1]])
            ax.fill(o[:, 0], o[:, 1], color=c)
            for h in getattr(G[i], "holes", []):
                ax.fill(h[:, 0], h[:, 1], color=BG)
            ax.set_aspect("equal"); ax.set_xlim(-.13, .13); ax.set_ylim(-.13, .13); ax.axis("off")
        ax = fig.add_axes([.70, .17, .275, .6], facecolor=BG)
        n = (g + 1) * 20
        ax.plot(np.arange(n), tr[:n], color=ORANGE, lw=3)
        ax.set_xlim(0, 200); ax.set_ylim(6.2, 6.7)
        ax.tick_params(colors=LIGHT, labelsize=13)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color(GREY)
        ax.set_xlabel("designs tried", color=LIGHT, fontsize=15); ax.set_ylabel("best predicted speed, m/s", color=LIGHT, fontsize=15)
        fig.text(.70, .90, f"Generation {g + 1} of 10", color="white", fontsize=22, weight="bold")
        fig.text(.70, .83, f"{tr[n - 1]:.2f} m/s", color=ORANGE, fontsize=25, weight="bold")
        enc.stdin.write(grab(fig))
        if t == len(fr) - 1:
            fig.savefig(OUT / "ga_final.png", facecolor=BG, dpi=100)
        plt.close(fig)
    enc.stdin.close(); enc.wait()


def flow():
    from scipy.interpolate import griddata
    from cfd.figures import _read_raw, read_vtk_polydata
    cases = {"flow_hole": (ROOT / "results/freeform/server_chute-b/video/free03_star_hole/postProcessing", "600", 1.4, 0.178),
             "flow_tilt": (ROOT / "results/cfd/canopy_test/q8_l015_r045_a10_L4/postProcessing", None, 2.6, 0.178)}
    for name, (pp, tn, zmax, D) in cases.items():
        td = pp / "planes" / tn if tn else sorted((pp / "planes").iterdir(), key=lambda p: float(p.name))[-1]
        d = _read_raw(td / "U_midY.raw")[1]
        pts, u = d[:, :3], d[:, 3:6]
        C = read_vtk_polydata(sorted((pp / "canopyP").glob("*/canopy.vtk"))[-1])[0]
        x0 = C[:, 0].mean(); z0 = C[:, 2].max() if name == "flow_tilt" else C[:, 2].min()
        xi = np.linspace(-1.2, 1.2, 420); zi = np.linspace(-.7, zmax, int(420 * (zmax + .7) / 2.4))
        XX, ZZ = np.meshgrid(xi, zi)
        px, pz = (pts[:, 0] - x0) / D, (pts[:, 2] - z0) / D
        keep = (px > -1.5) & (px < 1.5) & (pz > -1) & (pz < zmax + .2)
        Ux = griddata((px[keep], pz[keep]), u[keep, 0], (XX, ZZ)); Uz = griddata((px[keep], pz[keep]), u[keep, 2], (XX, ZZ))
        Sp = griddata((px[keep], pz[keep]), np.linalg.norm(u[keep], axis=1), (XX, ZZ))
        fig = plt.figure(figsize=(2.4 * 2.6, (zmax + .7) * 2.6), facecolor=BG)
        ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
        ax.imshow(Sp, origin="lower", extent=(xi[0], xi[-1], zi[0], zi[-1]), cmap="magma", vmin=0, vmax=9, aspect="auto", interpolation="bilinear")
        ax.streamplot(xi, zi, np.nan_to_num(Ux), np.nan_to_num(Uz), color=(1, 1, 1, .55), density=1.5, linewidth=.8, arrowsize=.7)
        sec = np.abs(C[:, 1]) < 0.004
        ax.scatter((C[sec, 0] - x0) / D, (C[sec, 2] - z0) / D, s=4, color="#7CF5FF", zorder=5)
        ax.set_xlim(xi[0], xi[-1]); ax.set_ylim(zi[0], zi[-1])
        fig.savefig(OUT / f"{name}.png", dpi=170, facecolor=BG); plt.close(fig)


def gallery():
    cfg = load_config(None)
    D = {d["name"]: d for d in json.load(open(ROOT / "results/freeform/designs_all.json"))}
    R = [r for r in csv.DictReader(open(ROOT / "results/freeform/final/analysis/free_table.csv")) if r["converged"] == "True"]
    R.sort(key=lambda r: float(r["speed"]))
    pick = R[:4] + R[-4:]
    fig, axs = plt.subplots(1, 8, figsize=(12.2, 2.05), facecolor=BG)
    for k, (ax, r) in enumerate(zip(axs, pick)):
        g = build_any_geometry(_design(D[r["name"]]), cfg)
        o = np.vstack([g.outline, g.outline[:1]])
        ax.fill(o[:, 0], o[:, 1], color=ORANGE if k < 4 else "#6E5A80")
        for h in getattr(g, "holes", []):
            ax.fill(h[:, 0], h[:, 1], color=BG)
        ax.set_aspect("equal"); ax.set_xlim(-.135, .135); ax.set_ylim(-.135, .135); ax.axis("off")
        ax.set_title(f"{float(r['speed']):.2f} m/s", color="white", fontsize=14, weight="bold" if k < 4 else "normal", pad=4)
    fig.subplots_adjust(0.002, 0, .998, .84, .06)
    fig.savefig(OUT / "gallery.png", dpi=170, facecolor=BG); plt.close(fig)
    # slits stay shut: inflated slit canopy
    z = max(shape_file(lambda d: not d.get("free") and not d.get("cut") and d.get("slit_len", 0) > 0.14 and d.get("q", 0) > 5), key=lambda q: q["tris"].shape[0])
    fig = plt.figure(figsize=(5, 4.2), facecolor=BG)
    X = z["X"] - np.r_[z["X"][:, :2].mean(0), 0]
    ax = canopy_axes(fig, [-.3, -.4, 1.6, 1.8], 0.085, 28, X[:, 2].mean())
    draw_canopy(ax, X, z["tris"])
    fig.savefig(OUT / "slit_3d.png", dpi=200, facecolor=BG); plt.close(fig)


if __name__ == "__main__":
    for job in sys.argv[2:] or ["inflate", "ga", "flow", "gallery"]:
        print(job, flush=True); globals()[job]()
