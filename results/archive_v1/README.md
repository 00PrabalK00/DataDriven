# Archive: v1 simulated drops (raw bundles deleted 2026-10-30 to free disk space)

**What it was.** Raw simulated-drop bundles of the v1 study (Oct 14-19 2026): MuJoCo drops with the virtual
RealSense + BNO085, run through the shared estimation pipeline. Aerodynamics = the heuristic `prior-v1`
map (**no CFD**), payload V1, 4 m drop. Evidence level L2: design rankings reflect the heuristic, not
physics, which is why v2 (CFD-informed) replaced it.

**Size deleted:** data/sim 7.6 GB, data/sim_remote 12.7 GB
(observation bundles: IMU CSV, LED events, RGB/depth frames for retained trials, estimated trajectories).

**Kept here:** 32401 drops (31843 with a valid fused pre-impact speed; 92 had frames retained).
- `v1_drops.csv.gz`: one row per drop: run, trial, seed, design (q, slit_len, slit_r or free-form radial),
  sync status, and every metric (pre-impact speed, lateral speed, landing offset, tilt, swing rate, peak g,
  deceleration label) for the camera / imu / fused modes, each with its status.
- `manifests.tar.gz`: full provenance manifest of every drop (seeds, configs, versions): any drop can be
  regenerated with the v1 code (git history) from it.
- `v1_drops_overview.png`: speed by run group, sensor-mode agreement, sampled design space, failure rates.
- Run-level results were already in `results/benchmark_full/` (summaries, request logs, convergence plots)
  and `results/studies/` (v1 representation/surrogate/flight studies); those are unchanged.

| Run group | Drops |
|---|---|
| gradient | 4579 |
| bo | 4560 |
| full_shard1 | 4560 |
| moo | 4440 |
| pso | 3857 |
| full_shard3 | 2245 |
| full_shard2 | 2242 |
| ga | 2095 |
| sa | 2080 |
| tabu | 240 |
| smoke | 190 |
| latent-param3 | 150 |
| latent-vae | 150 |
| latent-autoencoder | 144 |
| latent-pca | 138 |
| pilot | 100 |
| moo (fresh re-score) | 100 |
| bo (fresh re-score) | 90 |
| ga (fresh re-score) | 80 |
| pso (fresh re-score) | 80 |
| random (fresh re-score) | 80 |
| gradient (fresh re-score) | 60 |
| sa (fresh re-score) | 60 |
| tabu (fresh re-score) | 60 |
| smoke-fresh | 16 |
| screen | 2 |
| rt | 2 |
| checkA | 1 |
