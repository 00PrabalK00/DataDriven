"""Assemble results/REPORT.md from whatever result files exist (safe to rerun at any time).
Every section carries its evidence level (L1 software validation / L2 assumed aerodynamics)."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"


def table(path, cols=None, fmt=3, max_rows=40):
    p = R / path
    if not p.exists():
        return f"_(not available yet: `{path}`)_\n"
    rows = list(csv.DictReader(open(p)))
    if not rows:
        return "_(empty)_\n"
    cols = cols or list(rows[0].keys())

    def f(v):
        try:
            x = float(v)
            return f"{x:.{fmt}g}" if abs(x) < 1e4 else f"{x:.0f}"
        except (ValueError, TypeError):
            return str(v).strip('"')
    out = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for r in rows[:max_rows]:
        out += "| " + " | ".join(f(r.get(c, "")) for c in cols) + " |\n"
    return out


def text(path):
    p = R / path
    return p.read_text().strip() if p.exists() else f"(not available yet: {path})"


def img(path, alt):
    return f"![{alt}]({path})\n" if (R / path).exists() else f"_(figure not available yet: `{path}`)_\n"


def main():
    pilot = json.loads((R / "pilot/pilot_v3_payloadV1.json").read_text()) if (R / "pilot/pilot_v3_payloadV1.json").exists() else {}
    mp = json.loads((R / "payload/payload_v1_mass_properties.json").read_text()) if (R / "payload/payload_v1_mass_properties.json").exists() else {}
    jobs = R / "benchmark_full" / "jobs"
    done_runs = len(list(jobs.glob("full_job_*_runs.mat"))) if jobs.exists() else 0
    prog = f"{done_runs} of 80 (method, run) jobs completed (70 single-objective + 10 multi-objective); see table column 'runs'"
    md = f"""# Data-Driven Parachute Design — Simulation Phase Report

**Scope:** synthetic simulation phase (evidence levels **L1** and **L2** only). Rankings of *designs* below
reflect the heuristic aerodynamic prior (`prior-v1`), **not** real physics. Real design conclusions need
calibration (L3) and fresh physical drops (L4).

| Level | Meaning |
|---|---|
| L1 | software validation against known synthetic truth |
| L2 | synthetic benchmark under assumed aerodynamics |
| L3 | calibrated-model prediction (needs real drops) |
| L4 | physical demonstration (needs real drops) |

## 1. Payload V1 (from CAD)
Mass {mp.get('mass_kg', '?')} kg nominal (not weighed), COM (m) {[round(x, 4) for x in mp.get('com_m', [])]},
line azimuths (deg) {[round(x, 1) for x in mp.get('line_angles_deg', [])]}. Anchors = eyelet hole centres from the mesh.

{img('payload/payload_v1_rigid_body.png', 'payload')}

## 2. Feasibility (go/no-go, L2)
Decisions and full numbers: `results/DECISIONS.md`. Current config: 0.090 kg, 4 m drop.

{table('feasibility_v3_payloadV1/resolvable_by_mass_height.csv')}
{table('feasibility_v3_payloadV1/resolvable_by_slit_strength.csv')}
{img('feasibility_v3_payloadV1/feasibility_sweep.png', 'feasibility')}

**Reading:** with 3 repeats per design, design differences are only resolvable if slits have a strong
aerodynamic effect; under the prior-map or no-slit assumptions they are not.

## 3. Shared sensing pipeline (L1)
Single-drop validation against simulator truth (payload V1, 4 m): fused pre-impact speed error ≈ 0.04 m/s,
IMU-only ≈ 0.0001 m/s, camera-only ≈ 0.39 m/s (the camera sees only the last ~0.2 s; no markers fit on the
payload, so colour + depth tracking gives position only). Clock sync error ≈ 2 ms. All Python (pytest) and
MATLAB test suites pass (leakage, invalid handling, cache, budget accounting, determinism).

## 4. Timing / storage pilot
{json.dumps(pilot, indent=1) if pilot else '(not available)'}

## 5. Optimizer benchmark (L2) — 7 methods × 10 runs × max 200 evaluations × 5 scenarios
Progress: {prog}

{table('benchmark_full/full_summary.csv', ['method','runs','best_median','best_iqr','best_at25','best_at50','best_at100','best_at200','evals_to_target_median','frac_reached_target','requests_median','unique_designs_median','simulated_drops_median','sensing_failure_rate','fresh_score_median'], fmt=5)}
{img('benchmark_full/full_convergence_zoom.png', 'convergence (zoomed)')}

### Multi-objective (speed vs lateral speed)
{table('benchmark_full/moo_summary.csv', ['method','runs','best_median','hypervolume_median','spacing_median','requests_median'], fmt=5)}

## 6. Representation studies
PCA (rich r(θ) encoding, 64 samples):

{table('studies/rep_pca.csv')}
Autoencoder (held-out test split):

{table('studies/rep_ae.csv')}
VAE: {text('studies/rep_vae.txt')}

Same search (BO), same budget, different representations (simulator + sensing pipeline, L2):

{table('studies/latent_search.csv')}

## 7. Surrogates, sensitivity, flight-behaviour clusters (L2, benchmark data)
Leave-geometry-out cross-validation:

{table('studies/surrogate_cv.csv')}
Sobol indices (GP surrogate):

{table('studies/sobol.csv')}
{img('studies/interactions.png', 'interactions')}
k-means centroids of measured flight features:

{table('studies/flight_clusters.csv')}

## 8. Real2sim infrastructure (validated synthetically, L1)
{table('calibration/mismatch_study.csv')}
Parameter recovery note: in a 4 m drop, K_open and the opening time τ are ~0.99 correlated, so only their
combination is identifiable from height data; fix τ from video and fit the effective drag area.

## 9. Designs for the real drop test
{text('real_test/README.md').replace(chr(10)+'## ', chr(10)+'#### ').replace('# Real drop test', '### Real drop test')}

## 10. DOE and fabrication
18 designs (16 LHS + 2 unslit baselines), 54-drop randomized schedule (`results/doe/drop_schedule.csv`),
1:1 cutting templates (`results/doe/templates/`). The fabrication-gap comparison (L4) requires real drops.

## 11. Known limitations
* `prior-v1` aerodynamics are assumed; slits do not open in the rigid simulated canopy.
* Mass, line length, canopy mass and RealSense model are placeholders; contact model not yet calibrated.
* RGB regeneration matches up to small GPU rasterization differences; metrics agree.
* Part of the benchmark ran on a rented server (vast.ai): laptop GPU, server GPU (EGL) and server CPU (OSMesa) rendering.
  Remote vs local drops gave identical metrics. OSMesa vs GPU differed by ~0.0006 m/s, far below the 0.04 m/s pipeline noise.
  The backend is recorded in every drop manifest.
* Benchmark incomplete: runs per method are in the table (n); the remaining runs resume with `scripts/run_jobs.sh`.
"""
    (R / "REPORT.md").write_text(md)
    print("wrote", R / "REPORT.md")


if __name__ == "__main__":
    main()
