"""Slide figure: how the v2 pipeline fits together (design -> CFD-informed simulator -> sensors ->
shared estimation pipeline -> objective -> optimisers). Run: python/.venv/bin/python scripts/figures/pipeline_diagram.py"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parents[2] / "results" / "slides"
OUT.mkdir(parents=True, exist_ok=True)

C = {"design": "#e3f2fd", "phys": "#fff3e0", "sens": "#f3e5f5", "pipe": "#e8f5e9", "opt": "#fce4ec", "real": "#eeeeee"}
EDGE = "#37474f"


def box(ax, x, y, w, h, title, body, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=color, ec=EDGE, lw=1.4))
    ax.text(x + w / 2, y + h - 0.17, title, ha="center", va="top", fontsize=11.5, weight="bold", color="#212121")
    ax.text(x + w / 2, y + h - 0.52, body, ha="center", va="top", fontsize=8.6, color="#37474f", linespacing=1.35)


def arrow(ax, a, b, text="", dy=0.12, style="-|>", color=EDGE, ls="-"):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=16, lw=1.5, color=color, ls=ls))
    if text:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + dy, text, ha="center", fontsize=8.2, color=color, style="italic")


fig, ax = plt.subplots(figsize=(15, 7.2))
ax.set_xlim(0, 15); ax.set_ylim(0, 7.2); ax.axis("off")

# top row: design -> physics -> sensors -> pipeline -> objective
box(ax, 0.2, 4.2, 2.5, 2.2, "Design encoding", "3 numbers: shape q,\nslit length, slit radius\nor free-form outline\n(PCA / AE / VAE latent)\n250 cm² plastic, always", C["design"])
box(ax, 3.2, 4.2, 2.7, 2.2, "Drop physics", "MuJoCo rigid payload\n(CAD mass, 8 anchors)\n+ canopy, slack lines\nCFD-informed drag &\nstability map", C["phys"])
box(ax, 6.4, 4.2, 2.5, 2.2, "Virtual sensors", "BNO085 IMU 200 Hz\n(noise, bias, clipping)\nRealSense RGB-D\n(depth holes, blur,\ndropped frames)", C["sens"])
box(ax, 9.4, 4.2, 2.6, 2.2, "Shared pipeline", "same code for sim & real:\nLED clock sync,\nblob + depth tracking,\nerror-state EKF,\nimpact detection", C["pipe"])
box(ax, 12.5, 4.2, 2.3, 2.2, "Objective", "measured pre-impact\nspeed (5 scenarios)\n+ drift / failure\npenalties, invalid\n= marked penalty", C["pipe"])
for a, b in [((2.7, 5.3), (3.2, 5.3)), ((5.9, 5.3), (6.4, 5.3)), ((8.9, 5.3), (9.4, 5.3)), ((12.0, 5.3), (12.5, 5.3))]:
    arrow(ax, a, b)

# bottom row: CFD -> surrogate -> map ; optimisers ; real drops
box(ax, 0.2, 0.6, 2.5, 2.4, "CFD (OpenFOAM)", "form-found inflated\ncanopy (slits open)\nRANS k-ω SST, 7 m/s\nα = 0° and 10°\n→ drag area, pitch\nstability", C["phys"])
box(ax, 3.2, 0.6, 2.7, 2.4, "Surrogates + DOE", "Latin-hypercube DOE\npicks CFD shapes\nlinear / quadratic /\nGP / ensemble,\nleave-geometry-out CV\nSobol sensitivity", C["design"])
box(ax, 6.4, 0.6, 5.6, 2.4, "Optimisers (course methods)", "GA · multi-objective GA (NSGA-II)\nsimulated annealing · PSO · Bayesian optimisation\ngradient (SLSQP) · random baseline · tabu (extra)\nsame encoding, bounds, budget (200 evals), 10 runs each\nmetrics: best, evals-to-target, spread, failures, cost", C["opt"])
box(ax, 12.5, 0.6, 2.3, 2.4, "Real drops", "tiered designs\n(best / mid / worst)\nsame sensors +\nsame pipeline\n→ fabrication gap", C["real"])

arrow(ax, (2.7, 1.8), (3.2, 1.8))
arrow(ax, (4.55, 3.0), (4.55, 4.2))
ax.text(4.68, 3.6, "drag & stability\nmap", fontsize=8.2, color=EDGE, style="italic", va="center")
arrow(ax, (13.65, 4.2), (11.3, 3.0), "score", dy=-0.05)
arrow(ax, (6.6, 3.0), (1.45, 4.2))
ax.text(2.3, 3.62, "next design", fontsize=8.2, color=EDGE, style="italic")
arrow(ax, (12.0, 1.8), (12.5, 1.8), ls="--")
ax.text(12.25, 0.35, "top / mid / worst designs", ha="center", fontsize=8.2, color=EDGE, style="italic")
ax.text(7.5, 6.85, "Data-driven parachute design: simulation pipeline (v2)", ha="center", fontsize=15, weight="bold")
fig.savefig(OUT / "pipeline_overview.png", dpi=160, bbox_inches="tight")
print("wrote", OUT / "pipeline_overview.png")
