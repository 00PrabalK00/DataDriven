# Data-driven parachute design — simulation phase

Course project: *Comparative Evaluation of Data-Driven Design Methods for Parachute Shape and Slit
Optimization*. This build is the **synthetic simulation phase**: it demonstrates the shared sensing
pipeline and compares course methods **under assumed aerodynamics**. Physical calibration and fresh real
drops are still required before claiming a winning parachute or demonstrated sim2real transfer.

## Evidence levels (every output is tagged)
| Level | Meaning |
|---|---|
| L1 | software validation against known synthetic truth |
| L2 | synthetic benchmark under assumed aerodynamics (`prior-v1` heuristic map) |
| L3 | calibrated-model prediction, validated on held-out real geometries/drops |
| L4 | physical demonstration in fresh real drops |

## Layout
```
config/defaults.json      all parameters; entries listed under "placeholders" are NOT measured yet
python/chutesim/          geometry (single source of truth), aero prior map, MuJoCo scene/physics,
                          virtual BNO085 IMU, virtual RealSense RGB-D, drop writer, evaluator/cache, MATLAB bridge
python/pipeline/          SHARED sim/real estimation: bundle reader + truth guard, ArUco PnP / depth / fallback
                          detection, LED clock sync, ESEKF + RTS smoother, camera-only KF, metrics with status codes
python/validation/        the only code that reads simulator truth (separate process)
matlab/+chute/            DOE, ODE + fitting, real2sim infrastructure, optimizer benchmark, surrogates,
                          representation learning, sensitivity / clustering
matlab/scripts/           milestone drivers (m2 feasibility, m7 DOE, m9 benchmark, m10 studies)
scripts/                  test runner, replay video
```

## Sim/real contract: the observation bundle
`obs/<trial>/`: `imu.csv` (MCU clock), `led_events.csv`, `rgb/*.jpg`, `depth/*.npy` (raw z16, mm, depth
imager), `rgb_times.csv`, `depth_times.csv` (host clock, separate), `calib.json`, `meta.json` (rig/protocol).
Simulated truth lives in a separate `truth/` root marked `.TRUTH_ROOT`; seeds/provenance in `manifest/`.
Truth separation is **logical** (same OS user), enforced by `guard_path` and leakage tests.

## Running
```bash
cd python && uv sync
../scripts/run_tests.sh                       # Python tests (ROS plugin autoload disabled)
uv run chutesim drop --q 4 --slit-len 0.15 --slit-r 0.45 --run-root ../data/sim/manual
uv run chutesim evaluate --designs "[[4,0.15,0.45]]" --n-scenarios 5
uv run chutesim pilot --n-designs 10 --n-scenarios 5 --out ../results/pilot/pilot.json
uv run chutesim cache-audit
uv run python ../scripts/make_replay_video.py RUN_ROOT TRIAL out.mp4
```
MATLAB (R2026a; Optimization, Global Optimization, Statistics/ML, Deep Learning toolboxes):
```matlab
run('matlab/tests/runAll.m')       % test suite
run('matlab/scripts/m2_feasibility.m'); run('matlab/scripts/m7_doe.m')
SMOKE = true; run('matlab/scripts/m9_benchmark.m')   % checkpoint B
run('matlab/scripts/m10_studies.m')
```
MATLAB talks to Python through a **persistent separate Python process** (`pyenv ExecutionMode="OutOfProcess"`).

## Scoring rule (identical for every optimizer)
Score = min(mean measured pre-impact speed, S_cap) + capped drift and deceleration penalties. If any
required scenario has an invalid measurement, the candidate gets a marked infeasibility penalty above every
valid score; the speed is recorded as missing, never imputed. Measured speeds are never clipped.

## Known limitations
* `prior-v1` aerodynamics are heuristic; slits do not open in the rigid simulated canopy, so their effect
  comes only from the map. The rigid canopy cannot show inflation; the only deployment-related label is
  the observable "effective deceleration established".
* RGB regeneration is bit-identical except for rare GPU rasterization differences (a few grey levels on <1% of
  pixels; metrics agree); all other observation files are bit-identical in a pinned environment.
* Mass, drop height, line length, canopy mass and RealSense model are placeholders.
