# Real drop test: which designs to build and drop

Simulation (L2, assumed aerodynamics) picked one design. In the 33 completed benchmark runs it was found
independently by 5 runs of 3 different methods (tabu 1, GA 2, PSO 2-4). On the 5 search scenarios it
scores **6.905 m/s, against about 6.94 m/s for near-circular unslit designs** (a gap of about 0.035 m/s, about 0.5%).
It also held up on 20 fresh scenarios (6.821 m/s; the fresh scenarios are a different set, so compare only within one set).
The real test asks whether that holds, and *why*: is it the shape, the slits, or both?

## The 4 designs (2 x 2: shape x slits). Every canopy has exactly 250 cm² of plastic

| Code | Design | q | slit length (x R_eq) | slit radius (x R_eq) | What it tests |
|---|---|---|---|---|---|
| **A** | **Winner**: rounded square + 4 slits | 8 | 0.15 | 0.45 | the optimised design |
| B | rounded square, no slits | 8 | 0 | n/a | shape effect alone |
| C | circle + the same 4 slits | 2 | 0.15 | 0.45 | slit effect alone |
| D | circle, no slits (baseline, = DOE design 17) | 2 | 0 | n/a | reference |

Templates (1:1, print at 100% and check the 50 mm scale bar): `A_winner_q8_slits.svg`,
`B_square_noslits.svg`, `C_circle_slits.svg`, `D_circle_baseline.svg`. Black = outline cut, red = slit cuts
(knife cuts, no material removed). The square canopies are 160 mm across and the circles 178 mm.

## Drops
* 32 drops = 8 blocks x 4 designs, randomised within each block: `real_drop_schedule.csv`. Follow the order.
* Same setup as the simulator: 4.0 m release height, payload V1, 8 lines; full procedure in `../doe/DROP_DAY_PROTOCOL.md`.
* Record every drop, including failed ones, in the `notes` column. Never redo a bad drop silently.

## How to read the result
* A slower than D, in the 4 m pre-impact speed from the shared sensing pipeline, means the optimised design really helps (L4).
* Compare B and C with D to separate the shape effect from the slit effect.
* The predicted gap is small, about 0.035 m/s. With 8 drops per design the standard error of a mean is about sd/2.8.
  A gap this size is only detectable if real drop-to-drop scatter is below about 0.05 m/s. Check the scatter after the first 2 blocks
  and add blocks if needed. If real slits have a stronger effect than assumed (the feasibility sweep's "strong" case), the gap is larger.
* q = 8 is the upper limit of the search range, so the true optimum may be even squarer. If A wins clearly, a
  follow-up with q > 8 is worthwhile.
* Optional, for calibrating the simulator (L3): the 18-design DOE in `../doe/` (54 drops).
