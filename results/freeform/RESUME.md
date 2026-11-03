# Free-form CFD: paused 2026-10-30 17:20 EDT

State: 30 good runs of 142 (14 designs with both angles, 2 with one angle), 5 failed rows, 28 in-flight runs
discarded (OpenFOAM saves a case only when it finishes). Checkpoint: `results/freeform/checkpoint_2026-10-30_1720/`
and `results/freeform/server/cfd_free.csv` (checksum verified against the server). Form-found shapes:
`results/cfd/shapes/`, logs: `results/cfd/logs/`. Laptop pilot (8 cut-out designs, 16/16): `results/cutouts/pilot_cfd.csv`.

Instance 58441610 (vast, EPYC 7B12, 128 threads) was DESTROYED on 2026-10-30 at the user's request, after the
verified download. Everything needed is local and the batch resumes from cfd_free.csv on any new machine
(ok rows are skipped, failed rows rerun).

## Resume
1. Rent a new instance (EPYC 7B12 128 threads was good value), run the setup from the 10-30 notes (uv sync,
   scripts/v2/install_openfoam_native.sh), push python config assets scripts results/freeform, and copy
   cfd_free.csv to results/freeform/server/.
2. Update `~/.ssh/config` Host chute-vast with the new IP/port .
3. Start the watchdog: `VAST=<vastai> setsid nohup bash scripts/v3/vast_watchdog_cfd.sh <new_id> 12 0.15 &`
   It holds the instance at RUN_DONE; `touch results/v3_destroy_now` destroys it after a final copy.
4. On the server: `bash scripts/v3/run_free_cfd_retry.sh 28 4` (no pids to wait for) runs everything left,
   with the potentialFoam fallback. free03 at alpha 0.001 for the video:
   `CFD_BACKEND=native python ../scripts/v2/cfd_video.py --name free03_star_hole --design free03 --alpha 0.001 --procs 8`
   (start it separately; do not run the same design + angle twice at once).
112 runs left at ~73 min per round of 28: ~5 h, ~$2.70.
