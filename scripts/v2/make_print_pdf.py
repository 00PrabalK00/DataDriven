"""Print-ready 1:1 PDFs of the real-drop templates (one canopy per page, Letter and A4).

Reads results/real_test_v2/tiers.csv, rebuilds each geometry and draws it in true millimetres, with a 50 mm and
a 100 mm scale bar to check after printing. Print at "Actual size" / 100% (never "Fit to page").
  python/.venv/bin/python scripts/v2/make_print_pdf.py
"""
import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from chutesim.config import load_config  # noqa: E402
from chutesim.geometry import Design, build_geometry  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

PAGES = {"letter": (215.9, 279.4), "a4": (210.0, 297.0)}


def page(pdf, r, cfg, W, H):
    g = build_geometry(Design(r["q"], r["slit_len"], r["slit_r"]), cfg)
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(-W / 2, W / 2); ax.set_ylim(-H / 2, H / 2); ax.axis("off")
    cy = 15.0  # canopy centre slightly above page centre, text below
    # stencil: bold cut line (cut along its centre), slits with end ticks, crosshairs on the line holes
    o = np.vstack([g.outline, g.outline[:1]]) * 1000
    ax.plot(o[:, 0], o[:, 1] + cy, color="k", lw=1.6)
    for s in g.slits * 1000:
        ax.plot(s[:, 0], s[:, 1] + cy, color="red", lw=1.4, solid_capstyle="butt")
        u = (s[-1] - s[0]) / max(np.linalg.norm(s[-1] - s[0]), 1e-9)
        n = np.array([-u[1], u[0]]) * 1.5
        for e in (s[0], s[-1]):
            ax.plot([e[0] - n[0], e[0] + n[0]], [e[1] - n[1] + cy, e[1] + n[1] + cy], color="red", lw=0.8)
    if hasattr(g, "attach_points"):
        for p in np.asarray(g.attach_points) * 1000:
            ax.add_patch(plt.Circle((p[0], p[1] + cy), 2.0, fill=False, color="blue", lw=0.8))
            ax.plot([p[0] - 3, p[0] + 3], [p[1] + cy] * 2, color="blue", lw=0.5)
            ax.plot([p[0]] * 2, [p[1] + cy - 3, p[1] + cy + 3], color="blue", lw=0.5)
    ax.plot([-3, 3], [cy, cy], color="k", lw=0.5); ax.plot([0, 0], [cy - 3, cy + 3], color="k", lw=0.5)
    ax.text(0, cy + 4, r["code"], ha="center", fontsize=14, weight="bold", color="0.6")
    y0 = -H / 2 + 38
    x0 = -W / 2 + 18
    ax.text(x0, y0 + 22, f"{r['code']}  ({r['tier']})   q={float(r['q']):.2f}, slit len {float(r['slit_len']):.3f}, slit r {float(r['slit_r']):.2f}",
            fontsize=11, weight="bold")
    ax.text(x0, y0 + 15, f"net area {g.area_net * 1e4:.2f} cm².  How to cut: tape this sheet UNDER the clear plastic (or on top for opaque "
            "sheet).\n1. Cut along the centre of the black outline.  2. Knife-cut the red slits exactly between the end ticks "
            "(no material removed).\n3. Punch the 6 blue crosshairs (line points), keep >= 3 mm from the edge.  4. Write the code on the canopy.",
            fontsize=6.5, va="top", linespacing=1.5)
    for L, yy in ((50, y0), (100, y0 - 8)):
        ax.plot([x0, x0 + L], [yy, yy], color="k", lw=1.2)
        ax.plot([x0, x0], [yy - 1.5, yy + 1.5], color="k", lw=1.2); ax.plot([x0 + L, x0 + L], [yy - 1.5, yy + 1.5], color="k", lw=1.2)
        ax.text(x0 + L + 3, yy - 1.2, f"{L} mm: measure this after printing", fontsize=7)
    ax.text(x0, y0 - 18, "Print at 100% / Actual size (NOT 'fit to page').", fontsize=8, color="red", weight="bold")
    pdf.savefig(fig); plt.close(fig)


def main():
    cfg = load_config(None)
    rows = list(csv.DictReader(open(ROOT / "results/real_test_v2/tiers.csv")))
    for r in rows:
        for k in ("q", "slit_len", "slit_r"):
            r[k] = float(r[k])
    out = ROOT / "results/real_test_v2"
    for name, (W, H) in PAGES.items():
        with PdfPages(out / f"templates_{name}.pdf") as pdf:
            for r in rows:
                page(pdf, r, cfg, W, H)
        print(out / f"templates_{name}.pdf")


if __name__ == "__main__":
    main()
