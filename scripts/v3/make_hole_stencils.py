"""Print-ready 1:1 PDFs of the Oct 31 canopies with holes (one per page, Letter and A4), same format as
scripts/v2/make_print_pdf.py. Print at "Actual size" / 100% (never "Fit to page").
  python/.venv/bin/python scripts/v3/make_hole_stencils.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from cfd.batch import _design  # noqa: E402
from chutesim.config import load_config  # noqa: E402
from chutesim.cutouts import build_any_geometry  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

PAGES = {"letter": (215.9, 279.4), "a4": (210.0, 297.0)}
PICK = [("C0", "base_q2.8", "control, no holes"), ("V05", "vent05", "5% central vent"), ("V12", "vent12", "12% central vent"),
        ("F56", "free56", "best hand-sampled free-form"), ("W0", "win0", "best search winner, GA")]


def page(pdf, code, name, note, g, W, H):
    rot = np.array([[0, -1], [1, 0]]) if np.ptp(g.outline[:, 0]) > 190e-3 else np.eye(2)   # keep a printer margin
    pts = lambda p: np.asarray(p) @ rot.T * 1000
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(-W / 2, W / 2); ax.set_ylim(-H / 2, H / 2); ax.axis("off")
    cy = 30.0
    o = pts(np.vstack([g.outline, g.outline[:1]]))
    ax.plot(o[:, 0], o[:, 1] + cy, color="k", lw=1.6)
    for h in g.holes:
        c = pts(np.vstack([h, h[:1]]))
        ax.fill(c[:, 0], c[:, 1] + cy, facecolor="#f6d5d5", edgecolor="red", lw=1.4)
    for p in pts(g.attach_points):
        ax.add_patch(plt.Circle((p[0], p[1] + cy), 2.0, fill=False, color="blue", lw=0.8))
        ax.plot([p[0] - 3, p[0] + 3], [p[1] + cy] * 2, color="blue", lw=0.5)
        ax.plot([p[0]] * 2, [p[1] + cy - 3, p[1] + cy + 3], color="blue", lw=0.5)
    ax.plot([-3, 3], [cy, cy], color="k", lw=0.5); ax.plot([0, 0], [cy - 3, cy + 3], color="k", lw=0.5)
    y0 = -H / 2 + 38
    x0 = -W / 2 + 18
    ax.text(x0, y0 + 22, f"{code}   {note}   (CFD design {name})", fontsize=11, weight="bold")
    ax.text(x0, y0 + 15, f"net area {g.area_net * 1e4:.2f} cm².  How to cut: tape this sheet UNDER the clear plastic (or on top for opaque "
            "sheet).\n1. Cut along the centre of the black outline.  2. Remove every red shaded hole, cutting along its red line "
            "(this material comes out).\n3. Punch the blue crosshairs (line points), keep >= 3 mm from the edge.  4. Write the code on the canopy.",
            fontsize=6.5, va="top", linespacing=1.5)
    for L, yy in ((50, y0), (100, y0 - 8)):
        ax.plot([x0, x0 + L], [yy, yy], color="k", lw=1.2)
        ax.plot([x0, x0], [yy - 1.5, yy + 1.5], color="k", lw=1.2); ax.plot([x0 + L, x0 + L], [yy - 1.5, yy + 1.5], color="k", lw=1.2)
        ax.text(x0 + L + 3, yy - 1.2, f"{L} mm: measure this after printing", fontsize=7)
    ax.text(x0, y0 - 18, "Print at 100% / Actual size (NOT 'fit to page').", fontsize=8, color="red", weight="bold")
    pdf.savefig(fig); plt.close(fig)


def main():
    cfg = load_config(None)
    D = {d["name"]: d for d in json.load(open(ROOT / "results/freeform/designs_all.json"))}
    D.update({d["name"]: d for d in json.load(open(ROOT / "results/freeform/designs_win.json"))})
    out = ROOT / "drop_day_2026-10-31/1_print"
    for pname, (W, H) in PAGES.items():
        with PdfPages(out / f"templates_holes_{pname}.pdf") as pdf:
            for code, name, note in PICK:
                g = build_any_geometry(_design(D[name]), cfg)
                g.holes = getattr(g, "holes", [])
                assert g.feasible, name
                page(pdf, code, name, note, g, W, H)
        print(out / f"templates_holes_{pname}.pdf")


if __name__ == "__main__":
    main()
