# Real drop test v2: tiered designs from the CFD-informed simulation

Replaces `results/real_test/` (v1, chosen with the old heuristic model). Chosen with the **CFD surrogate**: a GP
on 36 OpenFOAM-simulated, form-found canopies, predicting the pre-impact speed after a 4 m drop with payload
V2 (0.095 kg nominal). See `tiers.csv` for each design's prediction.

| Tier | Codes | Predicted pre-impact speed | What they look like |
|---|---|---|---|
| Best | B1-B6 | 6.444-6.449 m/s | near-circular (q 2.3-2.9), very short or no slits |
| Middle | M1-M6 | 6.486-6.491 m/s | intermediate shapes, mixed slits |
| Worst | W1-W6 | 6.541-6.559 m/s | rounded squares (q 6.8-8), long slits |

Every canopy has exactly 250 cm² of plastic. Templates `templates/<code>.svg` are 1:1: print at 100% and check
the 50 mm bar. Black = outline cut, red = slit cuts (knife cut, no material removed), blue circles = the 6 line
attachment points (line azimuths 30, 90, 150, 210, 270, 330 deg, matching the payload's 6 slots).

## Drops
* 18 designs x 3 repeats = **54 drops**, in randomised blocks (`drop_schedule.csv`). Every block drops every
  design once, so drift over the day (wind, fatigue, battery) is spread over all tiers. Follow the order.
* 4.0 m release height, payload V2 flown **disc up, box down**, 6 lines of 0.35 m. Camera 1.8 m from the drop line, lens
  0.8 m high, **aimed 0.45 m above the pad** (pad visible in the frame). Hold still >= 1 s before release.
* Log every drop, failed ones too, in `notes`. Never redo a drop silently.
* Weigh the payload once (the simulation assumed 0.095 kg) and note it.

## How to read it (fabrication gap, week 11)
* Primary: **tier means** (18 drops each). The prediction is best < middle < worst by about 0.04 and 0.06 m/s.
  With drop-to-drop scatter s, the SE of a tier mean is about s/4.2, so tiers separate if s is roughly
  0.1 m/s or less.
* Secondary: rank correlation between predicted and measured speed over the 18 designs, the sim-to-real
  fabrication gap.
* If the real ranking holds: the CFD-informed simulator is useful for design (L3 after calibration). If it does
  not: calibrate (`matlab/+chute/+calib` / python port) on these drops and re-optimise. Both outcomes are results.
* Short slits barely open in CFD (< 1 mm gaps). Watch the high-speed video: if real slits flutter open, that is a
  physical effect the quasi-static model misses (note it!).
