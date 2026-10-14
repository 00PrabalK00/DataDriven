# Drop-day protocol (physical drops → L3 calibration and L4 fabrication gap)

This matches what the simulator assumes, so real logs go through the **same** pipeline
(`python/pipeline/`) without changes. If anything here has to change on the day, write it down
and update `config/defaults.json` before processing.

## Before the day
1. **Measure the placeholders** and put them in `config/defaults.json`:
   - payload mass, populated (config 0.090 kg, sweep 0.080–0.105);
   - suspension line length (config 0.35 m, 8 lines, tied to the 8 lid eyelets);
   - canopy mass for each cut design (plastic, 250 cm² net area);
   - exact RealSense model; choose a *supported* 848×480 @ 60 fps RGB + depth pairing.
2. **Cut the 18 canopies** from the 1:1 templates `templates/designXX.svg|dxf` (print at 100%,
   check the scale bar). Label each canopy with its design number. Designs 17 and 18 are the
   unslit baselines.
3. **Firmware:** BNO085 at 200 Hz, ±8 g, logging raw accel + gyro with MCU timestamps. The LED runs
   the pseudo-random blink code (seed 77, intervals 0.06–0.16 s, starting 0.05 s after logging
   starts). This is how the camera and IMU clocks are aligned.
4. Charge the battery and free up storage. Record one test drop and convert it to the bundle format below,
   then run it through the pipeline before the day. The real-log recorder and ingestion were deferred in the plan
   and still have to be written.

## Setup (match the simulated scene)
| Item | Value |
|---|---|
| Release height | **4.0 m** above the impact pad (measure to the payload bottom) |
| Release point | directly above the pad centre |
| Camera position | 1.8 m horizontally from the drop line, lens 0.8 m above the ground |
| Camera aim | at a point 0.7 m above the pad (it sees the last ~0.2 s before impact) |
| Streams | RGB + depth 848×480 @ 60 fps, both timestamps recorded |
| Background | plain and non-reflective; no people in the frame below 2 m |

Measure the actual camera pose (tape + level) and write it into `calib.json` for the session.

## Each drop (follow `drop_schedule.csv` order exactly, 54 drops)
1. Read the drop number, design and repeat from the schedule. The order is randomized with baselines interleaved, so don't re-order it.
2. Attach the canopy; check that all 8 lines are untangled and free.
3. Start IMU logging and RealSense recording. The LED must be visible in the first frames.
4. **Hold still for ≥ 1 s** (the stationary bias initialisation needs this), then release cleanly
   with no push or spin.
5. Let it settle for 2 s after impact, then stop both recordings.
6. Write in the `failure_label` column whatever you saw (tangled lines, canopy didn't open,
   hit something, LED hidden, dropped frames). Leave it empty if the drop was clean.
   **Never delete or redo a bad drop silently.** Log it, then repeat at the end if needed and mark it as a repeat.
7. Save the drop as an observation bundle:
   `data/real/<session>/obs/<trial>/` → `meta.json` (design, drop no., operator notes),
   `imu.csv`, `rgb/`, `depth/`, `rgb_times.csv`, `depth_times.csv`, `calib.json`.
   There is **no truth folder** for real drops.

## After the day
- Run the shared pipeline on every bundle. Speeds with status ≠ `ok` stay missing and are never refilled.
- Keep the calibration and validation designs disjoint (leave-geometry-out harness in `matlab/+chute/+calib`).
  Fit on the calibration designs only. Validate on held-out designs.
- Any refit after looking at validation results counts as a new iteration and needs fresh drops.
- For L4, cut the benchmark's best designs, drop them fresh, and compare predicted against measured speed and ranking.
