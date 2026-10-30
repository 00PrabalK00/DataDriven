# Next study: free-form canopies (outline + holes), CFD-informed

Why: CFD showed radial slits barely open (< 1 mm) and do nothing; holes (material removed) open under load
(form-finding: a 10% vent becomes 13.5% open area inflated). First pilot result: a 5% central vent gives
CdA 0.0241 m2 vs 0.0217 m2 for the same outline without a vent (+11%), because at fixed 250 cm2 of
plastic the vented canopy is larger (pilot still running, `pilot_cfd.csv`).

## Encodings (all exactly 250 cm2 net plastic; code in python/chutesim/)
| Family | Parameters | Code |
|---|---|---|
| superellipse + radial slits (v2, done) | 3 | geometry.py |
| superellipse + vent + ring of holes of any superellipse shape | 3 + 7 | cutouts.py |
| **free-form material field** (outline AND holes from one level set) | 9 (D6), 11 (C6), 15 (D3), 61 (no symmetry) | freeform.py |

Free-form: phi(x,y) = 1 - r^2 + sum_i w_i exp(-|p - c_i|^2 / 2 sigma^2), 61 Gaussian bumps on a hex grid;
plastic where phi > t, t solved so the main piece is exactly 250 cm2. Nothing about holes or outline is
prescribed. Fabrication rules: one piece, holes >= 0.3 cm2, no bridge thinner than 8 mm, no hole at the
line attachment points, span <= 30 cm. Random samples: 19/24 feasible (`freeform_gallery.png`).
Form-finding: free flaps flutter in the quasi-static model; the shape is averaged over the last 4000
iterations and the flutter amplitude is reported (0.4 mm in the test).

## Proposed study (course mapping)
| Step | Course topic | Work |
|---|---|---|
| encoding comparison: 3-param vs cut-out vs free-form | wk 2 encoding | done (code) |
| DOE: ~60 feasible free-form designs (LHS in weight space, D6) + 8 pilot designs, CFD at 0 and 10 deg | wk 2 DOE | ~136 CFD runs |
| PCA / autoencoder / VAE on the material fields | wk 3 | latent spaces for search |
| GP surrogate on CFD (CdA, Cm_alpha) | wk 6 | refit with shape features |
| GA, NSGA-II (slow descent vs stability, now a real trade-off), SA, PSO, tabu, BO in weight / latent space | wk 3-8 | surrogate benchmark |
| re-check winners in the full simulator (needs holes in the MuJoCo canopy mesh) | sim2real | later |

## Compute
| Option | ~136 CFD runs | Cost |
|---|---|---|
| laptop (4 cases x 4 cores, ~45 min each) | ~25 h | free |
| vast, 224-thread EPYC (28 cases x 4 cores, ~24 min each) | ~2-2.5 h incl. setup | ~$3 (credit $3.60, tight) |
| vast, cheaper 64-128 thread machine | ~4-5 h | ~$2-3 |
