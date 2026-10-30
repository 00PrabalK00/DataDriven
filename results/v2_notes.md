# v2 run notes (2026-10-30)

* CFD: the level-6 production mesh ran 5-12x slower than estimated on the rented 224-thread machine (memory
  bandwidth bound with 112 concurrent solver ranks): ~14 h for 72 cases. Restarted at level 5 (the level the
  disc/cup validation passed at: +5.5% / +6.7% vs Hoerner) with 600 iterations: 72/72 converged in ~70 min.
* OpenFOAM: the opencfd v2406 apt repository was mid-sync (broken index) on the server, so Ubuntu's OpenFOAM
  v1912 was used (hierarchical decomposition, no scotch). Re-validated on the server: disc Cd 1.235 (ref 1.17),
  cup 1.516 (ref 1.42), within 1% of the laptop's v2406 results.
* Full-simulator throughput on the server was ~3,300 drops/h (not ~19k/h as estimated), so the full 80-run
  x 200-eval x 5-scenario simulator benchmark (~89k drops, ~27 h) did not fit the $11.63 budget. As planned
  ("frozen surrogate" fallback), the complete optimizer comparison (8 methods x 10 runs x 200 evals) ran in
  the CFD-surrogate environment with measurement-like noise (SD 0.03 m/s, 1% invalid), reported separately;
  the full simulator was used for (a) re-scoring all 80 surrogate winners on 10 fresh scenarios, (b) a mini
  benchmark of all methods (3 runs x 60 evals x 3 scenarios), (c) a 400-design screen for the real-drop tiers,
  (d) the encoding comparison (BO in param3 / PCA / AE / VAE, 2 runs x 40 evals).
* Phase-2 trigger bug: the CFD-done wait matched its own launcher's command line (pgrep self-match), costing
  ~15 min; fixed by relaunching.

## 2026-10-30 05:22 EDT: phase 3 screen/verify timeout loop -> phase 3b
The screen (batch 50 x 3 = 150 drops) and verify (batch 80 x 10 = 800 drops) clients hit the 45 min client batch
timeout: under full load each connection's drops wait ~30 min per queue round, so a big batch needs > 45 min. On
timeout the client resends the whole batch while the server keeps running the abandoned one (no server-side reuse),
so both jobs restarted forever (screen.csv and verify_winners.csv were still empty after 1.5 h). Latent search had
finished normally. Fix: stopped run_phase3.sh + both clients, started scripts/v2/run_phase3b.sh (verify batch 4,
screen batch 10, CHUTESIM_REMOTE_BATCH_TIMEOUT=6 h), which waits for the still-running mini benchmark, then runs the
studies and RUN_DONE. Cost: ~1.5 h of the screen/verify share of the server, plus the orphaned batches finishing.
Lesson: batch timeout must scale with batch size x queue depth; or keep batches below the per-connection cap.
05:31 EDT: 3b replaced by scripts/v2/run_phase3c.sh. A single client gets at most 60 drops in flight (per-connection
cap), so one sequential screen/verify client would use 30-40 of 214 workers once the mini benchmark ends. 3c runs
the screen as 4 parallel parts (designs interleaved, batch 20 = 60 drops) and the 76 remaining verify designs as 2
parts (batch 6 = 60 drops), merges the part CSVs into screen.csv / verify_winners.csv, then studies + RUN_DONE.
06:51 EDT RUN_DONE; 07:23 EDT final sync (30 GB incl. retained frames -> data/v2_server/work) and instance 58353215
destroyed (vast shows 0 instances). Credit left $3.60 (started $11.63). Tiers re-run with the screen cross-check:
designs unchanged; full-sim screen confirms best < middle < worst with no overlap; surrogate vs full-sim Spearman
0.995 (374 screen designs), 0.985 (76 verified winners).

## 2026-10-30 evening: free-form CFD on vast 58441610 (EPYC 7B12, 128 threads, $0.53/h)
Round times ~60 min with 28 cases x 4 ranks. free11 (both angles): potentialFoam FPE on 28 highly skewed faces ->
cfd.case.run_stl retries without potentialFoam; failures rerun by scripts/v3/run_free_cfd_retry.sh. free03 a=0
failed because the CFD video ran the same design + angle at the same time (same case folder): my error; video
restarted at alpha 0.001 so the case name differs. The simulator env and v2 results are not affected.
