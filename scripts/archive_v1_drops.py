"""Archive the v1 simulated drops (data/sim, data/sim_remote) before deleting the raw bundles.

v1 = heuristic aero map (prior-v1, no CFD), payload V1, Oct 14-19 2026. Keeps per drop: run, trial, seed,
design, and every sensor-derived metric (camera / imu / fused mode, value + status), and all provenance
manifests. Output: results/archive_v1/ (v1_drops.csv.gz, manifests.tar.gz, figures, README.md).
  python/.venv/bin/python scripts/archive_v1_drops.py
"""
import csv
import gzip
import io
import json
import re
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = [ROOT / "data" / "sim", ROOT / "data" / "sim_remote"]
OUT = ROOT / "results" / "archive_v1"
METRICS = ["preimpact_vz", "lateral_speed", "landing_offset", "tilt_rms_deg", "tilt_max_deg", "swing_rate_rms",
           "peak_specific_force_g", "decel"]
MODES = ["camera", "imu", "fused"]


def run_label(name: str) -> tuple[str, str]:
    base = re.sub(r"-\d{8}-\d{6}-[0-9a-f]{6}$", "", name)
    m = re.match(r"full_job_([a-z]+)_\d+(-fresh)?$", base)
    if m:
        return base, m.group(1) + (" (fresh re-score)" if m.group(2) else "")
    return base, base.split("_")[0] if base.startswith("latent") else base


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, sizes = [], Counter()
    tbuf = io.BytesIO()
    with tarfile.open(fileobj=tbuf, mode="w:gz") as tar:
        for src in SRC:
            for run in sorted(p for p in src.iterdir() if p.is_dir()):
                base, group = run_label(run.name)
                sizes[src.name] += sum(f.stat().st_size for f in run.rglob("*") if f.is_file())
                if (run / "manifest").is_dir():
                    tar.add(run / "manifest", arcname=f"{src.name}/{run.name}/manifest")
                for mj in sorted((run / "est").glob("*/metrics.json")) if (run / "est").is_dir() else []:
                    trial = mj.parent.name
                    m = json.loads(mj.read_text())
                    meta_p = run / "obs" / trial / "meta.json"
                    d = json.loads(meta_p.read_text())["design"] if meta_p.exists() else {}
                    s = re.search(r"-s(\d+)-", trial)
                    r = {"source_dir": src.name, "run": run.name, "run_base": base, "group": group, "trial": trial,
                         "seed": int(s.group(1)) if s else "", "q": d.get("q"), "slit_len": d.get("slit_len"),
                         "slit_r": d.get("slit_r"), "radial": json.dumps(d.get("radial")) if d.get("radial") else "",
                         "sync_status": m.get("sync", {}).get("status"),
                         "frames_kept": (run / "obs" / trial / "rgb").is_dir()}
                    for mode in MODES:
                        mm = m.get("modes", {}).get(mode, {})
                        for k in METRICS:
                            v = mm.get(k, {})
                            r[f"{mode}_{k}"] = v.get("value") if isinstance(v, dict) else v
                            r[f"{mode}_{k}_status"] = v.get("status") if isinstance(v, dict) else ""
                    rows.append(r)
    (OUT / "manifests.tar.gz").write_bytes(tbuf.getvalue())
    with gzip.open(OUT / "v1_drops.csv.gz", "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    figures(rows)
    readme(rows, sizes)
    print(f"{len(rows)} drops archived -> {OUT}")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def figures(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ok = [r for r in rows if r["fused_preimpact_vz_status"] == "ok"]
    fig, axs = plt.subplots(2, 2, figsize=(13, 9))
    # 1 fused pre-impact speed by group
    g = defaultdict(list)
    for r in ok:
        g[r["group"]].append(_f(r["fused_preimpact_vz"]))
    keys = sorted(g, key=lambda k: np.median(g[k]))
    axs[0, 0].boxplot([g[k] for k in keys], vert=False, showfliers=False)
    axs[0, 0].set_yticks(range(1, len(keys) + 1), [f"{k} (n={len(g[k])})" for k in keys], fontsize=8)
    axs[0, 0].set_xlabel("fused pre-impact speed [m/s]")
    axs[0, 0].set_title("All v1 drops by run group (heuristic aero, payload V1)")
    # 2 camera vs imu vs fused
    both = [r for r in rows if all(r[f"{m}_preimpact_vz_status"] == "ok" for m in MODES)]
    f_ = np.array([_f(r["fused_preimpact_vz"]) for r in both])
    for m, c in (("camera", "#4c72b0"), ("imu", "#dd8452")):
        axs[0, 1].scatter(f_, np.array([_f(r[f"{m}_preimpact_vz"]) for r in both]) - f_, s=3, alpha=.3, c=c, label=f"{m} - fused")
    axs[0, 1].axhline(0, c="k", lw=.8)
    axs[0, 1].set_xlabel("fused pre-impact speed [m/s]")
    axs[0, 1].set_ylabel("difference [m/s]")
    axs[0, 1].set_title(f"Sensor modes vs fused estimate ({len(both)} drops valid in all modes)")
    axs[0, 1].legend(markerscale=4)
    # 3 design space coloured by speed (3-parameter designs)
    p3 = [r for r in ok if r["q"] not in (None, "", 0.0) and not r["radial"]]
    sc = axs[1, 0].scatter([_f(r["q"]) for r in p3], [_f(r["slit_len"]) for r in p3],
                           c=[_f(r["fused_preimpact_vz"]) for r in p3], s=6, cmap="viridis_r")
    plt.colorbar(sc, ax=axs[1, 0], label="fused pre-impact speed [m/s]")
    axs[1, 0].set_xlabel("q (2 = circle, 8 = square)")
    axs[1, 0].set_ylabel("slit length / R_eq")
    axs[1, 0].set_title("Where the v1 optimisers sampled (heuristic aero)")
    # 4 status rates per mode
    st = {m: Counter(r[f"{m}_preimpact_vz_status"] for r in rows) for m in MODES}
    labels = sorted({k for c in st.values() for k in c})
    bottom = np.zeros(len(MODES))
    for lab in labels:
        v = np.array([st[m][lab] / len(rows) * 100 for m in MODES])
        axs[1, 1].bar(MODES, v, bottom=bottom, label=lab)
        bottom += v
    axs[1, 1].set_ylabel("% of drops")
    axs[1, 1].set_title("Pre-impact speed status per sensing mode")
    axs[1, 1].legend(fontsize=8)
    fig.suptitle(f"v1 simulated drops archive: {len(rows)} drops (L2, heuristic aerodynamics, NO CFD)", weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "v1_drops_overview.png", dpi=130)


def readme(rows, sizes):
    grp = Counter(r["group"] for r in rows)
    ok = sum(r["fused_preimpact_vz_status"] == "ok" for r in rows)
    kept = sum(bool(r["frames_kept"]) for r in rows)
    lines = [
        "# Archive: v1 simulated drops (raw bundles deleted 2026-10-30 to free disk space)",
        "",
        "**What it was.** Raw simulated-drop bundles of the v1 study (Oct 14-19 2026): MuJoCo drops with the virtual",
        "RealSense + BNO085, run through the shared estimation pipeline. Aerodynamics = the heuristic `prior-v1`",
        "map (**no CFD**), payload V1, 4 m drop. Evidence level L2: design rankings reflect the heuristic, not",
        "physics, which is why v2 (CFD-informed) replaced it.",
        "",
        f"**Size deleted:** data/sim {sizes['sim'] / 1e9:.1f} GB, data/sim_remote {sizes['sim_remote'] / 1e9:.1f} GB",
        "(observation bundles: IMU CSV, LED events, RGB/depth frames for retained trials, estimated trajectories).",
        "",
        f"**Kept here:** {len(rows)} drops ({ok} with a valid fused pre-impact speed; {kept} had frames retained).",
        "- `v1_drops.csv.gz`: one row per drop: run, trial, seed, design (q, slit_len, slit_r or free-form radial),",
        "  sync status, and every metric (pre-impact speed, lateral speed, landing offset, tilt, swing rate, peak g,",
        "  deceleration label) for the camera / imu / fused modes, each with its status.",
        "- `manifests.tar.gz`: full provenance manifest of every drop (seeds, configs, versions): any drop can be",
        "  regenerated with the v1 code (git history) from it.",
        "- `v1_drops_overview.png`: speed by run group, sensor-mode agreement, sampled design space, failure rates.",
        "- Run-level results were already in `results/benchmark_full/` (summaries, request logs, convergence plots)",
        "  and `results/studies/` (v1 representation/surrogate/flight studies); those are unchanged.",
        "",
        "| Run group | Drops |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in grp.most_common()],
    ]
    (OUT / "README.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
