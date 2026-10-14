Plan: Data-Driven Parachute Design: Simulation Pipeline (Phase 1)

 Context

 This is a course group project titled "Comparative Evaluation of Data-Driven Design Methods for Parachute Shape and Slit Optimization." It asks two questions:
 1. Which canopy design gives the slowest pre-impact descent, with acceptable stability and deployment, under a fixed material budget?
 2. Which course methods find good designs most efficiently, reliably and accurately?

 The core rule: simulation and reality use matching observation types and processing. Both produce RGB-D frames plus BNO085 IMU samples, and both go through identical processing code. Their error
 distributions will still differ until calibration. Every score is derived from those observations. Simulator truth is kept separate from estimation through logical separation with leakage tests (see
 below).

 The directory /home/zuci/DataDriven is empty, so everything below is new.

 The environment has:
 - MATLAB R2026a with optim, globaloptim, stats, nnet, fusion, nav and vision.
 - Python 3.10 and uv.
 - An RTX 5060.
 - MuJoCo and OpenCV are not installed yet.

 Fixed decisions
 - A0 = 250 cm² (0.025 m²) of net plastic. Any 2D outline is allowed and there is no sheet-size limit. R_eq ≈ 8.92 cm.
 - The box is 0.08 × 0.08 × 0.20 m. Mass and drop height are unmeasured, so the config uses mass_kg = 0.15 and drop_height_m = 2.5, flagged "PLACEHOLDER".
 - The camera is a single Intel RealSense RGB-D. The model is configurable with a D435i-like default. Once the actual model is identified, the config must use one of its supported stream configurations:
   resolution, fps and RGB/depth pairing.
 - Scope: the full simulation pipeline, validated synthetically. Firmware, the RealSense recorder and real-log ingestion are deferred. The trial-bundle schema is their interface.

 Evidence levels (labeled on every output)

 Every figure, table and log carries one of these tags, and the report keeps them separate:
 - L1 Software validation. Code behaves correctly against known synthetic truth.
 - L2 Synthetic benchmark under assumed aerodynamics. Optimizer and representation performance on the uncalibrated simulator. Rankings of designs at L2 reflect the heuristics programmed into priorMap,
   not real physics.
 - L3 Calibrated-model prediction. Uses the simulator after real2sim fitting, validated on held-out real geometries and drops.
 - L4 Physical demonstration. Improvement measured in fresh real drops.

 This build reaches L1 and L2. Real2sim is described as "real2sim calibration infrastructure validated synthetically" until physical data exist.

 Modeling limitations (stated in code docs and the report)

 - Aero priorMap is a heuristic placeholder. It maps geometry features to K_initial, K_open, τ, rotational damping and a deployment-failure probability. It exists to exercise the software. Optimizers
   searching it will rediscover its built-in preferences, so all such rankings are tagged L2.
 - Slits do not physically open in the simulator. The canopy is a rigid light body, so zero-width slits exist only in the geometry description. All slit effects come entirely through the parameter map.
   Physical experiments are what establish slit effects.
 - The rigid canopy cannot show inflation. The rendered canopy always looks open, even while the aero model changes its deployment state. So visual detection would disagree with the modeled behavior. In
   this version, the only deployment-related label is the observable "effective deceleration established" (yes / no / invalid), taken from estimated drag versus free fall. Actual visual deployment
   detection is reserved for real footage, or for a later model with visible deployment motion.
 - Feasibility sweep reports a range, not a winner. It runs over a grid of aero assumptions: C_D range, slit-porosity effect from none to strong, opening τ range, and the mass/height placeholders. For
   each assumption set it reports the design-to-design landing-speed spread against expected estimation noise. With placeholders (K ≈ 0.02 + 0.007 m² for the box), landing speed is about 6.2 m/s versus
   7.0 m/s in free fall, so spreads may be only a few percent. The output is a go/no-go flag for the user. The levers are lighter mass and a higher drop.

 Architecture

 MATLAB owns geometry, aero maps, the ODE, DOE, optimizers, surrogates, representation learning and analysis. Python owns MuJoCo, virtual sensors and the shared pipeline.

 MATLAB reaches Python through a persistent separate Python process (pyenv(ExecutionMode="OutOfProcess")) that stays alive across calls to avoid startup cost. Every request and result is also written to
 disk as JSON/CSV, and a CLI batch mode is provided.

 DataDriven/
   config/defaults.json          constants, A0, mass/height (PLACEHOLDER), 8 lines + length, RealSense model + supported stream config,
                                 IMU spec (200 Hz, ±8 g, noise/bias), timestep, scenario distributions, objective limits, aero-assumption grid
   matlab/+chute/
     +geom/     superellipseOutline, solveScaleForArea, addRadialSlits, canonicalize (ℓ=0 ⇒ fixed r), checkFeasible (patches/edge/
                min bridge), richOutline (r(θ), 64 pts, area-normalized), exportTemplate (1:1 SVG/DXF), designToJson
     +aero/     priorMap (heuristic placeholder, L2), fittedMap (GP from calibration data, same interface)
     +ode/      simulateDrop (ode45 + ground event; m·v̇ = mg − ½ρ(K(t)+K_box)v|v|, exponential opening), fitAero (lsqnonlin, identifiable
                params only, e.g. effective K not C_D and A separately), feasibilitySweep (over aero-assumption grid)
     +doe/      lhsDesigns (16 LHS + 2 unslit baselines, feasibility rejection), dropSchedule (randomized, interleaved baselines, 54 drops)
     +bridge/   evaluate(designs, scenarioSet, env) → persistent Python process; env ∈ {simulator, frozenSurrogate}
     +bench/    budgetedObjective, runners (random, ga, simulannealbnd, particleswarm, bayesopt, tabuSearch [custom, discretized],
                fmincon [finite-diff calls counted, multistart within budget], gamultiobj/paretosearch), runBenchmark
     +calib/    real2sim fitting + leave-geometry-out validation harness; synthetic mismatch tests
     +surrogate/ linear/quadratic, GP (fitrgp), tree ensemble; leave-geometry-out CV
     +rep/      shape dataset generator (superellipse + Fourier perturbations + rounded polygons, area-normalized), PCA, AE, VAE
                (dlnetwork), reconstruction/validity metrics, latent-space search
     +analysis/ Sobol/Morris sensitivity + interactions, PCA on flight features, k-means on flight behaviors, convergence plots, tables
   python/ (uv project: mujoco, opencv-contrib-python, numpy, scipy; pyrealsense2 later)
     chutesim/                    simulator side; may see truth
       scene.py   MJCF: free-body payload (mass/COM/inertia from config), ground + compliant pad, rigid canopy body with outline
                  mesh (rendered for realism/occlusion only, never used for deployment labels), 8+8 sites, spatial tendons limited to [0, L] (slack allowed),
                  IMU site, RealSense camera, LED geom, ArUco-textured box faces
       aero.py    custom drag via xfrc_applied (K(t), box drag, rotational damping, stochastic oscillation); built-in fluid off (density=0)
       sensors.py IMU: BNO085 axes, bias + white noise + random walk, ±8 g clip, quantization, 200 Hz with jitter/dropouts, MCU clock
                  offset/drift
       camera.py  RealSense model: RGB + depth with separate intrinsics/extrinsics and **separate RGB and depth timestamps**; depth
                  noise ∝ z², **invalid pixels/holes**, edge flying pixels, **occlusion and alignment gaps when depth is mapped
                  into color** (implemented via real reprojection depth→color, not a mask shortcut), motion blur by sub-frame
                  averaging, dropped frames, LED sync flashes
       run_drop.py  writes the observation bundle to obs/<trial>/ and truth to a **separate truth root** (truth/<trial>/)
       evaluate.py  orchestrates: simulate → launch estimation worker on obs only → metrics → objective; multiprocessing pool
     pipeline/                    *** shared real/sim code ***
       worker.py  entry point; receives only the obs bundle path; refuses paths under the truth root; runs as a separate
                  subprocess with no truth path in argv/env. This is LOGICAL separation, not a security boundary (same OS
                  account). It is enforced by convention plus leakage tests (see Verification).
       bundle.py, sync.py (LED alignment of camera + MCU clocks; RGB/depth timestamp reconciliation)
       detect.py  ArUco PnP pose (primary); fallback colored-box segmentation + depth: the visible-surface centroid gets a geometric
                  correction toward box COM using estimated orientation/face normal and **inflated measurement covariance**
       ekf.py     error-state EKF: p, v, q, b_a, b_g; IMU propagation, camera updates, lever arm, stationary bias init;
                  camera-only / imu-only / fused
       decel.py   label "effective deceleration established" ∈ {yes, no, invalid} from estimated drag vs. free fall.
                  Never reads simulator deployment state. Visual deployment detection deferred to real footage.
       metrics.py contact time **detected from IMU impact signature + camera trajectory** (not MuJoCo contacts), pre-impact vertical
                  speed (fixed-window fit before detected contact), drift, tilt/swing, peak specific force + clipped flag, decel label.
                  Every metric carries a status: ok | invalid_tracking | invalid_contact | invalid_sync | clipped,
                  with a reason. Failures NEVER yield 0 or a default value.
     validation/                   separate process; the only code that reads truth: compares estimates with truth → error reports
     tests/
   data/cache/                  evaluation cache (key/manifest scheme below)
   data/sim/<run>/obs/<trial>/  meta.json (design, source, seeds, full provenance; no truth), imu.csv, rgb/, depth/, rgb_times.csv, depth_times.csv, calib.json
   data/sim/<run>/truth/<trial>/  truth.csv, contact events, assigned deployment state   (never passed to worker)

 The objective is identical for every optimizer and built only from pipeline outputs. It is the mean measured pre-impact vertical speed over a fixed scenario set (common random numbers). It is penalized
 when measured mean drift exceeds the limit or when the rate of "effective deceleration established = no" exceeds the baseline. Search uses S fixed scenarios, with S = 5 tentatively. Final designs are
 re-scored on fresh scenarios.

 Invalid-measurement handling, fixed before any run and identical for all optimizers:
 1. An invalid speed is recorded as missing, together with its reason. It is never replaced by 0 or by an imputed value.
 2. If any required scenario has an invalid speed, the candidate receives an explicitly marked infeasibility penalty. Measured speeds are never clipped or altered. Only the optimization score is bounded:
    - score = min(mean speed, S_cap) + bounded penalty terms, where S_cap = √(v0_max² + 2g·h_max) + margin, and v0_max is the configured maximum initial release speed;
    - the drift and deceleration penalties are each capped;
    - infeasibility penalty = S_cap + Σ(all penalty caps) + 1, which exceeds the complete valid score;
    - when a measured speed exceeds S_cap, it is logged as an estimation anomaly for investigation, not silently hidden.
 3. The mean speed is computed only for candidates whose required scenarios are all valid.
 4. Sensing failures (tracking, sync, contact detection) are reported separately from aerodynamic failures ("effective deceleration established = no"). Each method's run reports both rates.

 The penalty is an optimization score, never a fabricated speed measurement.

 Caching and reproducibility

 - Cache key = hash of:
   - the canonical geometry (full-precision float64-hex parameters plus the resulting polygon hash);
   - the scenario seed and scenario-distribution version;
   - the physical config (mass, COM, inertia, lines, pad, drop height, timestep);
   - the aero model ID and version, including the priorMap version or calibration-fit hash;
   - the sensor/camera config (IMU spec, RealSense stream config, noise params);
   - the pipeline version (the git commit of pipeline/ plus estimator settings);
   - the simulator versions (MuJoCo, chutesim).
 - Invalidation: a change to any component changes the key, so stale results are never reused. Each cache entry stores its full provenance manifest. A cache audit command lists entries made with outdated
   components.
 - Partial reuse: a pipeline-only change re-runs estimation on stored observation bundles if they are retained. Otherwise the observations are regenerated deterministically from the stored seed and
   config.
 - Finite-difference safety: canonicalization only merges truly identical geometries, namely ℓ=0 slits and exact duplicates. The cache key uses the full-precision parameters (float64 hex), not rounded
   values. So the small perturbations fmincon uses for finite differences always produce distinct keys and fresh evaluations. A test confirms that a 1e-6 perturbation is a cache miss.
 - Raw-frame retention: when frames are discarded to save disk, keep the manifest, seeds, configs, IMU CSV, timestamps and metrics. That is enough to regenerate the observations. Bit-identical
   regeneration is guaranteed only in a pinned environment. The manifest records:
   - uv.lock and the MATLAB version;
   - the MuJoCo version;
   - renderer settings and backend (EGL);
   - GPU, driver, CPU and OS.

   In a different environment, regenerated observations are compared within numerical tolerances. Original bundles are kept for every reported result. Complete bundles are always preserved for baselines,
   every design that appears in a reported result, and a random sample of the rest.

 Benchmark accounting and scope

 - Budget: each run has a maximum of 200 evaluations. A run may stop earlier on valid convergence, which is recorded. The best-so-far value is logged at 25, 50, 100 and 200 evaluations.
 - Three counters per run, logged separately:
   - objective requests (cached hits still count as algorithm requests);
   - unique designs;
   - actual simulated drops (requests × scenarios minus cache hits).
 - Infeasible geometries are logged as requests flagged invalid, which feeds the valid-geometry rate.
 - Full volume: 7 methods × 10 runs × 200 × 5 scenarios = 70,000 simulated drops. Final re-scoring and the representation studies come on top of that.
 - Timing and storage pilot before committing. Measure seconds per drop and bytes per bundle, including RGB-D frames, for about 50 drops. Then project wall-clock time on 20 cores and the disk total, and
   present both to the user.
   - Options if the full volume is too heavy: fewer scenarios or runs, lower-resolution renders, or deleting raw frames after metrics, keeping a sample.
   - Frozen surrogate: this is the other fallback. Train a surrogate on pipeline outputs and run every compared method in that same environment. Report it as a separate benchmark, "surrogate
     environment," and never mix it with simulator-environment results.

 Real2sim (infrastructure, validated synthetically)

 - Parameter recovery: data comes from the same model, so this checks implementation only (L1).
 - Deliberate model mismatch: generate data with structure the fitted model lacks, for example:
   - a non-exponential opening;
   - drag ∝ v^1.8;
   - velocity-dependent porosity;
   - line elasticity;
   - unmodeled sensor bias drift.

   Then fit and check how the frozen model predicts held-out geometries. This shows how errors appear when the model is wrong.
 - The harness for real data is ready: calibration drops and geometries are kept disjoint from validation drops and geometries, so validation never reuses fitting data. Any refit after validation is
   logged as a new iteration that needs fresh validation.

 Course-topic coverage

 ┌────────────────────────────────┬──────────────────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────┐
 │             Topic              │                              Implementation                              │                                      Evaluated by                                      │
 ├────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ Design encoding                │ +geom 3-param superellipse + slits; rich r(θ)                            │ expressiveness, valid-design rate, fabrication difficulty                              │
 ├────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ DOE                            │ +doe LHS + baselines, randomized schedule                                │ coverage (discrepancy), usefulness for surrogates                                      │
 ├────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ Sensitivity                    │ +analysis Sobol/Morris                                                   │ main and interaction indices (L2 until calibrated)                                     │
 ├────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ PCA                            │ flight-feature PCA; rich-shape PCA                                       │ variance retained, reconstruction loss                                                 │
 ├────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ K-means                        │ +analysis on measured flight features                                    │ cluster validity, interpretability                                                     │
 ├────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ Autoencoder                    │ +rep AE on r(θ)                                                          │ reconstruction accuracy, geometric validity                                            │
 ├────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ VAE                            │ +rep VAE, latent sampling + search                                       │ diversity, validity, evaluated performance                                             │
 ├────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ Surrogates                     │ +surrogate                                                               │ leave-geometry-out error                                                               │
 ├────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ GA, SA, PSO, BO, Tabu,         │ +bench runners                                                           │ best result, evaluations to target, run-to-run spread, runtime, start/setting          │
 │ Gradient                       │                                                                          │ sensitivity                                                                            │
 ├────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ Multi-objective                │ gamultiobj/paretosearch: speed vs stability (impact g only once          │ hypervolume, spread                                                                    │
 │                                │ validated)                                                               │                                                                                        │
 ├────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ Fabrication gap                │ templates + validation harness (L4 later)                                │ predicted vs measured, rank preservation                                               │
 └────────────────────────────────┴──────────────────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────┘

 Milestones

 Acceptance checkpoint A: one complete simulated drop yields:
 - RGB-D frames;
 - IMU samples;
 - a reconstructed trajectory, from camera-only, IMU-only and fused estimation;
 - sensor-derived metrics.

 Checkpoint B is the small optimizer smoke test. Both checkpoints come before any scaling.

 1. Setup: uv project, MuJoCo and OpenCV, MATLAB pyenv (out-of-process), config.
 2. Geometry and ODE, plus the feasibility sweep over the aero-assumption grid. This is a go/no-go report to the user.
 3. MuJoCo scene: tendon slack, ODE parity, and 1 ms vs 0.5 ms convergence.
 4. Virtual IMU and RealSense renderer with the full depth imperfection model, plus the obs/truth bundle writer.
 5. Shared pipeline: worker isolation, detection, EKF, observable contact and deployment, metrics, and a separate validation process.
 6. Evaluator with the three counters, the provenance-keyed cache and invalid handling, plus the timing/storage pilot. Present the projected volume to the user before scaling up.
 7. DOE, drop schedule and fabrication templates.
 8. Real2sim infrastructure: recovery tests, model-mismatch tests and the disjoint-split harness.
 9. Optimizer benchmark (L2): convergence plots (median and IQR) and the results table.
 10. Representation, surrogate, sensitivity and k-means studies (L2).

 Verification

 - uv run pytest python/tests checks:
   - tendons go slack;
   - drag is applied once;
   - MuJoCo matches ode45 within 1%;
   - 1 ms and 0.5 ms runs agree;
   - IMU clips at ±8 g;
   - depth holes and occlusion appear at expected silhouette edges;
   - RGB/depth timestamps are distinct;
   - leakage tests:
     - the worker raises when given a truth path;
     - argv and env contain no truth path;
     - an audit hook (sys.addaudithook) running during worker tests fails on any open() under the truth root;
     - metrics are byte-identical when the truth root is deleted or moved before estimation;
   - contact and the deceleration label come only from observations;
   - invalid handling: forced tracking loss or contact-detection failure gives status invalid with speed missing. Any single invalid required scenario yields the marked infeasibility penalty, which
     exceeds every valid objective. Sensing failures and aerodynamic failures are counted separately;
   - cache: changing any key component misses the cache; a 1e-6 parameter perturbation misses the cache; regenerating from seeds is bit-identical in the pinned environment;
   - EKF RMSE in each mode stays below thresholds in the validation process;
   - the COM-correction fallback gives a bias reduction with larger covariance.
 - MATLAB runtests('matlab/tests') checks:
   - area = 250 cm² to 1e-9;
   - q = 2 gives a circle;
   - zero-slit designs are canonicalized;
   - infeasible slits are rejected;
   - LHS bounds hold;
   - the schedule is randomized;
   - fitAero recovers its own synthetic parameters;
   - under mismatch, the mismatch report is produced;
   - the budget wrapper caps at 200;
   - cached requests are counted;
   - finite-difference calls are counted;
   - the three counters are consistent.
 - End-to-end smoke test: 2 methods × 2 runs × 25 evals produces convergence plots tagged "L2 synthetic benchmark under assumed aerodynamics". One drop is replayed in the MuJoCo viewer with its RGB-D
   frames, ArUco detections and depth holes overlaid.

