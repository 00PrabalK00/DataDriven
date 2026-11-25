# CLAUDE.md: project handoff (read first)

Course group project for NYU ROB-GY 7863B (Data-Driven Design): *Comparative Evaluation of Data-Driven
Design Methods for Parachute Shape and Slit Optimization*.
Team (speaking order on Nov 3): Pranav Lavande (PL3236), Walter Kimball (WSK6251), Prabal Khare (PK3391).
This repo belongs to Prabal (GitHub 00PrabalK00/DataDriven, **public**). Last handoff written 2026-11-25.

The two questions: (1) which canopy lands slowest, with acceptable stability, from a fixed 250 cm² of plastic?
(2) which course methods find good designs most efficiently and reliably?

## How the user wants to work
- Answer timing, queue, progress and ETA questions as **tables**.
- Heavy compute goes on **rented vast.ai machines**, not the laptop (the laptop runs another paper's experiments).
  CFD needs no GPU, so compare physical CPU cores per dollar. Ask before destroying a machine. Don't pay for idle GPUs.
- Keep evidence levels separate. L1 = software check, L2 = simulation under assumed or CFD aero,
  L3 = calibrated on real drops, L4 = fresh real drops. Everything so far is L1/L2. Never claim a winning
  parachute from simulation alone. Label results "simulation estimates; physical validation pending".
- Invalid measurements get a marked infeasibility penalty, never a made-up value.
- New decisions get appended to `results/DECISIONS.md`.
- Slides: no "01/02" corner tags, no audience question/vote slides, should not look AI-made, use videos and graphs.
- Before the Nov 3 talk only course weeks 1-8 were allowed (no gradient methods, no fabrication gap).
  Weeks 10-12 (method selection, gradient, fabrication gap, state of the art) are now fair game.
- Course slides and schedule: `docs/course/` (local only, not on GitHub; don't publish them, the repo is public).

## Fixed setup
- 250 cm² net plastic, any 2D outline. Drop height 4 m (at 2.5 m designs could not be told apart; see DECISIONS.md).
- 6 suspension lines. Payload about 95 g and canopy 3 g are **assumed, not weighed**.
- Sensing: one Intel RealSense RGB-D (exact model still unknown) plus a BNO085 IMU on an ESP32-S3
  (`firmware/imu_logger/`). Sim and real share the same processing code: `python/pipeline/`
  (ESEKF + RTS smoother, LED clock sync, metrics with status codes). Truth separation with leakage tests.

## History
| Version | What | Where |
|---|---|---|
| v1 (Oct 13-16) | MuJoCo drop simulator, virtual RealSense + IMU, shared pipeline, heuristic aero map, 3-variable superellipse + slits, MATLAB benchmark | `python/chutesim`, `matlab/`, `results/REPORT.md` |
| v2 (Oct 29-30) | OpenFOAM CFD (simpleFoam k-omega SST, 7 m/s, 0° and 10°) on form-found canopies feeds the simulator. 8 methods × 10 runs × 200 evals in the surrogate env. Real-drop tiers | `results/RESULTS_2026-10-30.md`, `results/v2_notes.md`, `results/benchmark_v2`, `results/studies_v2` |
| v3 (Oct 30-Nov 2) | Slits found useless (< 1 mm opening under load), so: 7-variable cut-outs, then 9-variable free-form field. CFD on free-form designs, GP on shape features, 7-method benchmark, 5 winners re-checked with CFD | `results/freeform/`, `results/cutouts/`, `scripts/v3/` |

CFD validation: flat disc Cd 1.235 vs 1.17, cup 1.516 vs 1.42 (Hoerner, *Fluid-Dynamic Drag*). Mesh level 5.

### Encodings
- **3 variables:** q (2-8, 2 = circle), slit_len (0-0.25), slit_r (0.25-0.65).
- **7 variables:** vent_frac, hole_frac, n_holes, hole_r, hole_aspect, hole_p, hole_rot_deg (on top of the base q).
- **9 variables (free-form, `python/chutesim/freeform.py`):** φ = 1 − (r/R_eq)² + Σ w·Gaussian over 61 bumps
  on a hex grid. D6 symmetry links them into 9 weights (±1.6). Plastic is φ > t, with t found by bisection so the
  area is exactly 250 cm². This is a standard level-set/RBF method plus symmetry linking, **not novel**.
  The sandcastle animation `presentation/midway_2026-11-03/media/sand.mp4` explains it (`scripts/v3/deck_sand.py`).

### v3 pipeline
1. LHS designs, then a fabrication check (78% of free-form samples can be cut).
2. Inflation scan of 780 shapes (64% stable) trains a random-forest classifier (77% accuracy).
3. Form-finding (`python/cfd/formfind.py`, quasi-static, uniform pressure, one-way coupled), then CFD at 0° and 10°.
   130 runs, 51 stable designs, 45 converged.
4. GP surrogate on 7 shape features predicts CdA and Cm_alpha. Landing speed comes from CdA in closed form.
   Leave-one-out rank correlation 0.80 for CdA.
5. Search methods optimise the surrogate (200 evals × 10 runs, 0.03 m/s noise). They never see physics.
6. Winners are re-checked with fresh CFD.

### Key results (L2, simulation)
| Design | Landing speed (CFD) |
|---|---|
| 12% central vent (hand-made) | **6.31 m/s**, lowest checked |
| Best search winner (GA) | 6.33 (surrogate predicted 6.27) |
| Plain canopy | 6.45 |
| 49% open free-form | 7.20 |

- The vent is 0.14 m/s slower than plain and has 54% less pitch instability, but is not self-righting.
  Only 4 of 45 designs are self-righting (the best of those is 6.91).
- About 10% open area looks best. Past 30% open, drag falls away.
- The surrogate was optimistic by 0.06-0.17 m/s on the 3 GA winners. The 2 winners from other methods were within 0.01.
- Benchmark medians (m/s): GA 6.260, PSO 6.271, multi-objective GA 6.288, BO 6.293, SA 6.303, random 6.312, tabu 6.475.
- Dimensionality reduction on 1,883 shape masks: at 9-D, autoencoder IoU 0.97 and PCA 0.94. VAE samples are 66% one piece.
- Free fall from 4 m: 8.9 m/s. 3 repeats per design detect a gap of 0.139 m/s (assuming 0.06 m/s noise), so more repeats are needed.

## Midway presentation (Nov 3, done)
- Deck: `presentation/midway_2026-11-03/parachute.pptx` (16 slides, 4 embedded videos, source lines
  bottom-right, speaker notes in SAY / IF ASKED form with speaker names).
- Speakers: Pranav slides 1-5 and 14, Walter 6-9 and 15, Prabal 10-13 and 16.
- It is the user's LibreOffice-edited file. Change it with `scripts/v3/patch_user_deck.py`, which patches in place,
  rather than rebuilding from `scripts/v3/build_deck.js` (that would lose the user's edits).
  `parachute_midway_2026-11-03.pptx` is the older generated build.
- Script + Q&A guide (Claude Doc): https://claude.ai/artifact/3QHDuZkwbLipwx4KEMSxC8

## Not done yet / next steps
- **Real drops have not been done.** `drop_day_2026-10-31/drop_log.csv` is empty. The kit is in
  `drop_day_2026-10-31/START_HERE.md`. Still needed: weigh the payload, IMU wiring, identify the RealSense model,
  write the recorder, add the hole stencils (`scripts/v3/make_hole_stencils.py`) to the schedule.
- Planned next: feed the CFD checks back into the surrogate (BO), multi-objective GA (NSGA-II) for the speed vs
  stability Pareto front, then real drops decide.
- Known limits: Cm_alpha is a two-angle slope, there is no CFD-to-shape feedback, and the surrogate is trained
  on only about 40 free-form designs.

## Files not in git
| What | Size | Where |
|---|---|---|
| `results/cfd/cases/` (OpenFOAM cases) | 2.8 GB | GitHub release `data-2026-11-25` (tar.xz) and USB zip |
| `data/cache/` (evaluation cache) | 328 MB | GitHub release `data-2026-11-25` and USB zip |
| `data/v2_server/work/` (raw simulated frames from the v2 server run) | 30 GB | old laptop only. Summaries are in `results/`. Regenerable from seeds |
| `docs/course/` (course slides) | 41 MB | USB zip only (not for a public repo) |
| `python/.venv` | — | rebuild with `cd python && uv sync` |

## Running
```bash
cd python && uv sync            # Python 3.10; MuJoCo, torch CPU, pymoo, scikit-learn
../scripts/run_tests.sh
bash scripts/v2/install_openfoam_native.sh   # only if you need CFD (OpenFOAM v2406)
```
Rebuilding deck media needs Node with pptxgenjs + jszip, and ffmpeg (imageio-ffmpeg works).
See `README.md` for the v1 simulator CLI and MATLAB scripts.
