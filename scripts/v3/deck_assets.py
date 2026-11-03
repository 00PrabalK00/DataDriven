"""Stills for the Nov 3 deck that deck_media.py does not make.
  python/.venv/bin/python scripts/v3/deck_assets.py
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from cfd.batch import _design  # noqa: E402
from chutesim.config import load_config  # noqa: E402
from chutesim.cutouts import build_any_geometry  # noqa: E402
from chutesim.geometry import Design, build_geometry  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = ROOT / "presentation/midway_2026-11-03/media"
BG, LIGHT, ORANGE = "#15091F", "#E9DDF2", (255, 138, 61)


def main():
    cfg = load_config(None)
    D = {d["name"]: d for d in json.load(open(ROOT / "results/freeform/designs_all.json"))}
    tier = next(r for r in csv.DictReader(open(ROOT / "results/real_test_v2/tiers.csv")) if r["code"] == "M3")
    slit = build_geometry(Design(float(tier["q"]), float(tier["slit_len"]), float(tier["slit_r"])), cfg)
    for name, g in (("enc_param", slit), ("enc_cut", build_any_geometry(_design(D["holes6_circle08"]), cfg)),
                    ("enc_free", build_any_geometry(_design(D["free27"]), cfg))):
        fig, ax = plt.subplots(figsize=(3, 3), facecolor=BG)
        o = np.vstack([g.outline, g.outline[:1]])
        ax.fill(o[:, 0], o[:, 1], color=LIGHT)
        for h in getattr(g, "holes", []):
            ax.fill(h[:, 0], h[:, 1], color=BG)
        for s in g.slits:
            ax.plot(s[:, 0], s[:, 1], color=BG, lw=2.2)
        ax.set_aspect("equal"); ax.axis("off")
        fig.savefig(OUT / f"{name}.png", dpi=220, facecolor=BG, bbox_inches="tight", pad_inches=0.02); plt.close(fig)
    # shapes for the audience votes
    D.update({d["name"]: d for d in json.load(open(ROOT / "results/freeform/designs_win.json"))})
    for name in ("free07", "base_q2.8", "vent12", "free52", "win0"):
        g = build_any_geometry(_design(D[name]), cfg)
        fig, ax = plt.subplots(figsize=(3, 3), facecolor=BG)
        o = np.vstack([g.outline, g.outline[:1]])
        ax.fill(o[:, 0], o[:, 1], color=LIGHT)
        for h in getattr(g, "holes", []):
            ax.fill(h[:, 0], h[:, 1], color=BG)
        ax.set_aspect("equal"); ax.set_xlim(-.125, .125); ax.set_ylim(-.125, .125); ax.axis("off")
        fig.subplots_adjust(0, 0, 1, 1)
        fig.savefig(OUT / f"quiz_{name}.png", dpi=220, facecolor=BG); plt.close(fig)
    # one weight changed: the centre weight opens a hole with nothing else touched
    from chutesim.freeform import build_free_geometry, free_design
    for name, w9 in (("weight_0", 0.0), ("weight_hole", -1.6)):
        g = build_free_geometry(free_design([0.0] * 8 + [w9], "D6"), cfg)
        fig, ax = plt.subplots(figsize=(3, 3), facecolor=BG)
        o = np.vstack([g.outline, g.outline[:1]])
        ax.fill(o[:, 0], o[:, 1], color=LIGHT)
        for h in g.holes:
            ax.fill(h[:, 0], h[:, 1], color=BG)
        ax.set_aspect("equal"); ax.set_xlim(-.125, .125); ax.set_ylim(-.125, .125); ax.axis("off")
        fig.subplots_adjust(0, 0, 1, 1)
        fig.savefig(OUT / f"{name}.png", dpi=220, facecolor=BG); plt.close(fig)
    # VAE samples from the rep study, recoloured for the dark slides
    im = Image.open(ROOT / "results/freeform/server_chute-a/rep/rep_overview.png").convert("L")
    W, H = im.size
    k = W / 1920
    a = np.asarray(im.crop((int(1197 * k), int(163 * k), int(1903 * k), int(428 * k))), float)
    a = np.clip((235 - a) / 170, 0, 1)[..., None]
    bg = np.array([0x15, 0x09, 0x1F], float)
    Image.fromarray(np.uint8(bg * (1 - a) + np.array(ORANGE, float) * a)).resize((1412, 530), Image.LANCZOS).save(OUT / "vae_samples.png")


if __name__ == "__main__":
    main()
