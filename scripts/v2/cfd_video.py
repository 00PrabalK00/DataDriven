"""CFD video: time-accurate (pimpleFoam) wake behind one canopy, |U| on the y = 0 plane, as MP4 + GIF.

The steady RANS runs give one picture; this continues one case in physical time (k-omega SST, U = 7 m/s) and
samples the mid plane every --dt seconds, so the unsteady wake (vortex shedding behind the canopy) is visible.
  python/.venv/bin/python scripts/v2/cfd_video.py --name base_q2.8 --q 2.8 [--cut 0.1,0,0,0,1,2,0] --procs 8
Output: results/cfd/video/<name>/ (postProcessing, logs, result.json) and results/media/v2/cfd_<name>.mp4/.gif
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def render(log_dir: Path, out_stem: Path, title: str, D: float = 0.178) -> int:
    import cv2
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image
    from scipy.interpolate import griddata
    from cfd.figures import _read_raw, read_vtk_polydata
    tdirs = sorted((log_dir / "postProcessing" / "planes").iterdir(), key=lambda p: float(p.name))
    t0 = float(tdirs[0].name)
    tdirs = [t for t in tdirs if float(t.name) > t0 + 1e-9] or tdirs   # skip the steady snapshot
    P, _, _ = read_vtk_polydata(sorted((log_dir / "postProcessing" / "canopyP").glob("*/canopy.vtk"))[-1])
    cen = P.mean(0)
    cx, cz = float(cen[0]), float(cen[2])
    xi = np.linspace(cx - 1.2 * D, cx + 1.2 * D, 240)
    zi = np.linspace(cz - 0.8 * D, cz + 4.0 * D, 480)
    XI, ZI = np.meshgrid(xi, zi)
    sec = np.abs(P[:, 1]) < 0.004
    frames, vw = [], None
    for k, td in enumerate(tdirs):
        _, d = _read_raw(td / "U_midY.raw")
        x, z = d[:, 0], d[:, 2]
        m = (np.abs(x - cx) < 1.4 * D) & (z > cz - 1.0 * D) & (z < cz + 4.3 * D)
        sp = griddata((x[m], z[m]), np.hypot(d[m, 3], d[m, 5]), (XI, ZI), method="linear")
        fig, ax = plt.subplots(figsize=(5.2, 8.4), dpi=110)
        im = ax.pcolormesh((XI - cx) / D, (ZI - cz) / D, sp, cmap="inferno", shading="auto", vmin=0, vmax=9)
        ax.plot((P[sec, 0] - cx) / D, (P[sec, 2] - cz) / D, ".", color="cyan", ms=2)
        ax.set_aspect("equal")
        ax.set_xlabel("x / D")
        ax.set_ylabel("z / D  (flow upwards, 7 m/s)")
        ax.set_title(f"{title}\nt = {float(td.name) - t0:.3f} s", fontsize=10)
        fig.colorbar(im, ax=ax, shrink=0.6, label="|U| [m/s]")
        fig.tight_layout()
        fig.canvas.draw()
        img = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy()
        plt.close(fig)
        if vw is None:
            h, w = img.shape[:2]
            vw = cv2.VideoWriter(str(out_stem) + ".mp4", cv2.VideoWriter_fourcc(*"mp4v"), 15, (w, h))
        vw.write(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        frames.append(Image.fromarray(img).resize((img.shape[1] // 2, img.shape[0] // 2)))
    vw.release()
    frames[0].save(str(out_stem) + ".gif", save_all=True, append_images=frames[1:], duration=66, loop=0)
    return len(frames)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--q", type=float, default=2.8)
    ap.add_argument("--slit-len", type=float, default=0.0)
    ap.add_argument("--slit-r", type=float, default=0.45)
    ap.add_argument("--cut", default=None, help="comma list: vent_frac,hole_frac,n_holes,hole_r,aspect,p,rot")
    ap.add_argument("--design", default=None, help="take the design with this name from --designs (any family)")
    ap.add_argument("--designs", default=str(ROOT / "results" / "freeform" / "designs_all.json"))
    ap.add_argument("--alpha", type=float, default=0.0)
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--level", type=int, default=5)
    ap.add_argument("--t", type=float, default=0.6, help="transient physical time [s]")
    ap.add_argument("--dt", type=float, default=0.005, help="frame interval [s]")
    ap.add_argument("--render-only", action="store_true")
    a = ap.parse_args()
    from chutesim.cutouts import CutDesign
    from cfd.case import SolverParams, run_case
    if a.design:
        from cfd.batch import _design
        des = _design(next(d for d in json.loads(Path(a.designs).read_text()) if d.get("name") == a.design))
    else:
        des = CutDesign(a.q, a.slit_len, a.slit_r, None, tuple(float(v) for v in a.cut.split(",")) if a.cut else None)
    log_dir = ROOT / "results" / "cfd" / "video" / a.name
    if not a.render_only:
        r = run_case(des, a.alpha, a.procs, a.level, sample=True, log_dir=log_dir,
                     solver=SolverParams(n_iter=600, transient=True, force_transient=True, t_transient=a.t,
                                         sample_dt=a.dt))
        (log_dir / "result.json").write_text(json.dumps(r, indent=1, default=str))
        print({k: r.get(k) for k in ("rc", "rc_transient", "solver_used", "CdA_m2", "runtime_s")})
    out = ROOT / "results" / "media" / "v2" / f"cfd_{a.name}"
    out.parent.mkdir(parents=True, exist_ok=True)
    n = render(log_dir, out, f"{a.name}: time-accurate CFD (pimpleFoam, k-omega SST)")
    print(f"{n} frames -> {out}.mp4 / .gif")


if __name__ == "__main__":
    main()
