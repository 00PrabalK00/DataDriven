# Project decisions log

## 2026-10-13 — Drop height raised to >= 4 m (feasibility sweep v1)

**Decision (user):** drop from **4 m or higher**. Config `drop.height_m` = 4.0 (minimum; exact height TBD).

**Evidence:** feasibility sweep v1 (`results/feasibility_v1_heights_2.0-4.0/`), evidence level
L2 (assumed aerodynamics), 18 DOE designs, A0 = 250 cm², 243 assumption sets
(C_D scale {0.6,0.8,1.0} x slit-effect strength {0,1,3} x opening-time scale {0.5,1,2} x mass x height).
Detection threshold: best-vs-worst landing-speed spread > 4 x SE with per-drop noise 0.06 m/s and
3 repeats per design (= 0.139 m/s).

| mass / height | mean landing speed (free fall) | median spread | max spread | resolvable sets |
|---|---|---|---|---|
| 0.10 kg / 2.0 m | 5.66 (6.26) m/s | 0.020 | 0.081 | 0/27 |
| 0.10 kg / 2.5 m | 6.18 (7.00) m/s | 0.028 | 0.108 | 0/27 |
| 0.10 kg / 4.0 m | 7.28 (8.86) m/s | 0.053 | 0.186 | 6/27 |
| 0.15 kg / 2.0 m | 5.85 (6.26) m/s | 0.014 | 0.058 | 0/27 |
| 0.15 kg / 2.5 m | 6.43 (7.00) m/s | 0.020 | 0.079 | 0/27 |
| 0.15 kg / 4.0 m | 7.73 (8.86) m/s | 0.040 | 0.144 | 2/27 |
| 0.20 kg / 2.0 m | 5.95 (6.26) m/s | 0.011 | 0.046 | 0/27 |
| 0.20 kg / 2.5 m | 6.56 (7.00) m/s | 0.016 | 0.062 | 0/27 |
| 0.20 kg / 4.0 m | 7.99 (8.86) m/s | 0.032 | 0.116 | 0/27 |

Overall resolvable: 8/243 (3%); at the old placeholders (0.15 kg, 2.5 m): 0/27; with no slit effect: 0/81.
All resolvable sets are 4 m drops with the strong slit-effect assumption.
Remaining levers if 4 m is still insufficient: lighter payload (~0.10 kg), more repeats per design,
larger net area (fixed at 250 cm² by the assignment choice).

## 2026-10-13 — Feasibility sweep v2: drop heights 4, 5, 6 m

`results/feasibility_v2_heights_4-6/` (L2, same 18 designs, 243 assumption sets, same threshold 0.139 m/s).

| mass / height | mean landing speed | median spread | max spread | resolvable sets |
|---|---|---|---|---|
| 0.10 kg / 4 m | 7.28 m/s | 0.053 | 0.186 | 6/27 |
| 0.10 kg / 5 m | 7.78 m/s | 0.069 | 0.235 | 9/27 |
| 0.10 kg / 6 m | 8.16 m/s | 0.083 | 0.280 | 9/27 |
| 0.15 kg / 4 m | 7.73 m/s | 0.040 | 0.144 | 2/27 |
| 0.15 kg / 5 m | 8.37 m/s | 0.053 | 0.187 | 6/27 |
| 0.15 kg / 6 m | 8.89 m/s | 0.066 | 0.230 | 9/27 |
| 0.20 kg / 4 m | 7.99 m/s | 0.032 | 0.116 | 0/27 |
| 0.20 kg / 5 m | 8.71 m/s | 0.043 | 0.154 | 3/27 |
| 0.20 kg / 6 m | 9.31 m/s | 0.054 | 0.192 | 6/27 |

Overall resolvable: 50/243 (21%). By slit-effect assumption: none 0/81, prior-map strength 0/81,
strong (3x prior) 50/81. Conclusion: going higher and lighter helps, but differences become detectable
with 3 repeats only if slits have a strong aerodynamic effect. Under the prior-map assumption (strength 1)
no mass/height combination up to 6 m is resolvable with 3 repeats per design.

## 2026-10-13 — Payload V1 adopted (CAD handoff) + feasibility sweep v3

**Decision (user):** simulate the actual payload V1 (CAD: `assets/payload_v1/body.stl`, `lid.stl` =
"Data Driven-Body001(3).stl"; pin not supplied, 0.16 g ignored). One rigid body, nominal mass 0.090 kg
(NOT weighed; sweep 0.080–0.105 kg), COM/inertia from a parts model, 8 line anchors = eyelet hole
centres extracted from the mesh (r = 3 mm, z = 13 mm, azimuths 26.1/63.9/... deg). No ArUco markers
(no face large enough); camera tracks by colour + depth (position only). Contact time constant
stiffened to 2 ms (8 ms let the light payload pass through the 20 mm pad at ~7 m/s).
Details: `results/payload/payload_v1_mass_properties.json`, picture `payload_v1_rigid_body.png`.

Feasibility v3 (`results/feasibility_v3_payloadV1/`, L2, threshold 0.139 m/s, 3 repeats):

| mass / height | mean landing speed | median spread | max spread | resolvable sets |
|---|---|---|---|---|
| 0.080 kg / 4 m | 6.91 m/s | 0.059 | 0.206 | 8/27 |
| 0.080 kg / 5 m | 7.31 m/s | 0.075 | 0.253 | 9/27 |
| 0.080 kg / 6 m | 7.60 m/s | 0.090 | 0.294 | 9/27 |
| 0.090 kg / 4 m | 7.08 m/s | 0.056 | 0.195 | 6/27 |
| 0.090 kg / 5 m | 7.52 m/s | 0.071 | 0.242 | 9/27 |
| 0.090 kg / 6 m | 7.85 m/s | 0.086 | 0.284 | 9/27 |
| 0.105 kg / 4 m | 7.28 m/s | 0.050 | 0.179 | 6/27 |
| 0.105 kg / 5 m | 7.79 m/s | 0.066 | 0.226 | 9/27 |
| 0.105 kg / 6 m | 8.17 m/s | 0.080 | 0.269 | 9/27 |

Overall 74/243 (30%); at the current config (0.090 kg, 4 m) 6/27 (22%). By slit-effect assumption:
none 0/81, prior-map 0/81, strong 74/81. Same conclusion as v2: physical comparisons with 3 repeats can
only separate designs if slits have a strong aerodynamic effect.
