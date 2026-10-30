# Plan v2: full-Python pipeline with CFD-informed aerodynamics (target: mid-way presentation, Nov 3)

Why v2: (1) the simulator's shape -> aerodynamics map (`prior-v1`) is a heuristic guess, so its design
rankings say nothing physical; (2) MATLAB (student licence) cannot run on rented machines, so the laptop's
RAM capped the benchmark at ~8 parallel runs (~8-10 h). v2 replaces the heuristic with a CFD-trained
surrogate and ports every MATLAB method to Python so everything runs on one rented machine.
Everything from v1 that still holds is kept (payload, sensors, shared pipeline, evaluator/cache, tests).

## 0. Scope: course topics -> what we deliver

| Week | Course topic | Delivered in v2 |
|---|---|---|
| 2 | Encoding | 3-param superellipse+slits vs free-form r(theta); valid-design rate, expressiveness, cuttability |
| 3 | Dim. reduction, autoencoders | PCA, AE, VAE on 3,000 area-normalised outlines (reconstruction, validity, diversity) |
| 4 | GA + multi-objective GA | GA; NSGA-II for slow descent vs stability; hypervolume, spacing |
| 6 | SA, surrogates, PSO | SA, PSO; linear/quadratic/GP/ensemble surrogates with leave-geometry-out CV |
| 7-8 | Bayesian optimisation | GP-EI BO (+ BO in PCA/AE/VAE latent spaces = encoding comparison) |
| 10 | Method review & selection | benchmark table: best, evaluations-to-target, run-to-run spread, failures, cost |
| 11 | Gradient + fabrication gap | SLSQP with counted finite differences; tiered designs + templates for real drops (drops after Nov 3) |
| 12 | Emerging approaches | CFD-informed surrogate as a physics prior, VAE generative design |
| extras | (not in the course) | tabu search, Sobol sensitivity, k-means on flight features (kept, marked as extras) |

## 1. Python port of all MATLAB methods (laptop, ~0.5 day)

New package `python/ddd/` ("data-driven design"); MATLAB code stays as the reference.

| MATLAB | Python | Fidelity note |
|---|---|---|
| `BudgetedObjective` | `ddd.budget.BudgetedObjective` | same 3 counters (requests / unique designs / simulated drops), cache hits counted, budget cap 200, best-so-far at 25/50/100/200, checkpoint traces |
| random | own | batches of 10 uniform designs |
| `ga` (pop 20, stall 50) | pymoo GA | pymoo default operators (SBX/PM) differ from MATLAB's scattered crossover; documented |
| `gamultiobj` (pop 20) | pymoo NSGA-II | same algorithm family |
| `simulannealbnd` (T0=100) | own SA following MATLAB's documented defaults (exp. cooling 0.95^k, step ~ sqrt(T), reannealing) | |
| `particleswarm` (swarm 15) | own PSO following MATLAB's defaults (adaptive inertia 0.1-1.1, self/social 1.49) | |
| `bayesopt` (EI-plus, 10 seeds) | own GP-EI on scikit-learn GP (ARD Matern 5/2, like MATLAB) incl. EI-plus overexploitation rule | |
| `fmincon` sqp, FD step 1e-2, multistart | scipy SLSQP, same FD step, FD calls counted, multistart within budget | |
| `tabuSearch.m` | port of our own code | extra |
| `runBenchmark`, `summarize`, `convergencePlot`, `hypervolume2d` | `ddd.bench` | same table columns, fresh-scenario re-score of each run's best (20 scenarios) |
| `lhsDesigns`, discrepancy, `dropSchedule` | scipy.stats.qmc | |
| `pcaStudy`, `aeStudy`, `vaeStudy`, `shapeDataset`, `latentSearch` | scikit-learn + PyTorch (GPU on the server) | |
| `fitModels`, `leaveGeometryOutCV`, `sobolIndices`, `flightClusters` | scikit-learn + own Saltelli estimator | |

Tests (pytest), ported from `matlab/tests`: budget cap at 200, cached requests counted, FD calls counted,
counters consistent, hypervolume on a known front, Sobol on the Ishigami function, LHS bounds, schedule
randomised, area = 250 cm^2. Plus a cross-check: each method on the same analytic test function in MATLAB
(laptop) and Python, compared by median best and spread (implementations differ; the picture must agree).

## 2. Aerodynamics from CFD (laptop setup ~1 day, server ~2-4 h)

1. **Inflated canopy shape (form-finding):** the 2D cut outline is turned into a 3D canopy by a
   mass-spring membrane relaxation (dynamic relaxation): plastic sheet with the real outline and real
   slits, 8 lines of the real length to the payload anchors, uniform pressure load. Slits are real cuts in
   the mesh, so under load they open into slots. Output: a closed 1 mm-thick surface (STL).
   Assumption (stated in the report): one-way coupling, no flutter, quasi-static shape.
2. **CFD:** OpenFOAM (opencfd Docker image on the server), snappyHexMesh around the STL, incompressible
   RANS k-omega SST, U = 7 m/s (pre-impact speed), Re ~ 8e4. Each shape at angle of attack 0 deg and
   10 deg -> drag area CdA (descent speed) and pitching-moment slope Cm_alpha (static stability: negative =
   self-righting). Steady solver with force averaging; transient fallback if it does not settle.
3. **CFD validation** before any design runs: flat disc (Cd ~ 1.1-1.2) and hemispherical cup
   (Cd ~ 1.3-1.4) against published values (Hoerner, Fluid-Dynamic Drag). If off by > 15%, fix the
   mesh/turbulence setup first.
4. **Which shapes:** Latin-hypercube DOE of ~30 shapes over (q, slit length, slit radius) + ~10 free-form
   shapes from the VAE/PCA space + the 4 real-test designs. ~44 shapes x 2 angles = ~88 CFD runs.
5. **CFD surrogate:** GP (and the other surrogates, compared by leave-geometry-out CV) from geometry
   features -> CdA and Cm_alpha. Features (not raw encodings) so one model serves both encodings.
6. **New aero map `cfd-v1`** (same interface as `prior-v1`): K_open from CdA, oscillation intensity from
   Cm_alpha. Opening time tau and deployment-failure probability have no CFD basis: kept from prior-v1 and
   labelled as assumptions. The map file carries its own hash, so cache keys separate it from prior-v1.

## 3. Runs on one rented machine (vast.ai, ~$10-15 total)

Machine: >= 192 cores, GPU with >= 24 GB (lesson: an 8 GB card cannot hold hundreds of render contexts),
>= 200 GB RAM. All drops go through the existing drop server (GPU pool for small batches, CPU/OSMesa pool
for large ones); the 80 optimizer runs are light Python clients on the same machine.

| Run | Content | Est. time |
|---|---|---|
| R1 | CFD batch (~88 cases) | 2-4 h |
| R2 | **Surrogate-environment benchmark**: 8 methods x 10 runs x 200 evals on the CFD surrogate | minutes |
| R3 | **Full simulator benchmark** (cfd-v1 aero + sensors + pipeline): 8 methods x 10 runs x 200 evals x 5 scenarios, all 80 runs in parallel, + fresh re-score | 2-3 h |
| R4 | Encoding comparison: BO in param3 / PCA / AE / VAE spaces, 3 runs each, full simulator | ~1 h |
| R5 | Studies: surrogate CV, Sobol, k-means/PCA flight features, representation metrics | < 1 h |

Data handling (lessons from v1): metrics written to the local cache as they arrive; raw logs synced every
10 min; final sync when credit < $1; instance destroyed after the final sync. Credit alert to the user
below $2.

## 4. Deliverables for Nov 3 (simulation results only)

* `results/REPORT_v2.md` + figures: CFD validation, example inflated shapes + flow fields, surrogate
  accuracy, Sobol, optimiser benchmark (both environments), Pareto front, encoding comparison,
  representation metrics; v1 heuristic-model results kept as a baseline section.
* Mid-way slides (~12-15 slides, course-topic structure) + speaker notes.
* Every result labelled by evidence level: CFD-informed simulation is still L2 (no real-drop calibration).
* Real-test plan updated from the new ranking: 5-10 best / 5-10 middle / 5-10 worst designs, 1:1
  templates, randomised drop schedule (for weeks 11-12).

## 5. Timeline

| Day | Work |
|---|---|
| Oct 30 | Python port + tests; form-finding; OpenFOAM disc/cup validation (laptop) |
| Oct 31 | rent machine: CFD batch -> surrogate -> cfd-v1 -> R2 -> R3 (overnight) |
| Nov 1 | R4, R5, MATLAB cross-check, report + figures |
| Nov 2 | slides, buffer |

## 6. Risks and fallbacks

| Risk | Fallback |
|---|---|
| OpenFOAM setup/convergence slips | validate on disc/cup first; transient solver; fewer shapes (20) |
| Form-finding unstable for odd free-form shapes | use only the 3-param DOE for CFD; free-form via surrogate features |
| CFD spread between shapes tiny | report it honestly (consistent with bluff-body physics); stability (Cm_alpha) becomes the main differentiator, multi-objective takes centre stage |
| vast GPU/EGL issues | CPU/OSMesa pool only (measured ~37 s/drop) |
| Credit runs out | metrics already local; queue resumes |

## 7. Not in scope before Nov 3
Physical drops, IMU flashing + Allan recording, RealSense recorder, real-to-sim calibration (all planned for
weeks 10-12; firmware and Allan analysis already written).
