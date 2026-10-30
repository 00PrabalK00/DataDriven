# Prior-art brief: data-driven design of small parachute canopies (shape + slits)

*Quick-mode research brief (deep-research, 2026-10-30). Sources were found by web search and their identity
checked (title, venue, year, DOI or stable URL). Where only a secondary source or an abstract was seen, this is
marked. Numbers marked "secondary" must be checked in the original before they go into the final report.*

## Research question
What is already known about (1) canopy planform vs drag/stability, (2) slots/vents (geometric porosity),
(3) CFD/FSI of parachutes, (4) optimisation and surrogate-based design of decelerators, (5) small-scale drop
experiments with on-board sensing, (6) comparisons of GA/SA/PSO/BO on engineering problems, and what does it
imply for our project and for our CFD finding that round canopies give the most drag and that short slits
barely open under load?

## 1. Planform (outline) vs drag and stability
- **Knacke, T. W. (1992). *Parachute Recovery Systems Design Manual* (NWC TP 6575). Para Publishing.**
  The standard design handbook (also DTIC ADA247666). Tabulates drag and oscillation for flat circular,
  conical, cross, ribbon, ringslot, etc. Secondary report of its Fig. 5-20: drag coefficient rises with
  suspension-line length ratio up to ~2. *Implication:* our fixed line length (0.35 m vs ~0.18 m canopy, ratio
  ~2) sits near the drag optimum; line length is a lever we did not vary.
- **Hoerner, S. F. (1965). *Fluid-Dynamic Drag*.** Secondary sources: flat disc Cd ≈ 1.17, square plate ≈ 1.16,
  hemispherical cup (open side to flow) ≈ 1.4. *Implication:* for rigid flat shapes the outline barely
  matters (disc ≈ square), but a cupped shape has ~20% more drag than a flat one. Our CFD validation (disc
  1.235, cup 1.515, +5–7%) reproduces these. The drag gain of round canopies in our CFD most likely comes from
  **how deeply they inflate (cup depth)**, not from the outline itself. That is consistent with flat-plate
  physics and a useful interpretation for the slides.
- **Cruciform vs annular, DSTA Singapore (Young Defence Scientists Programme report).** CFD reports a higher
  drag coefficient and stability for cruciform than annular canopies, while a US patent on cruciform designs
  (US 7,261,258) states typical cruciform canopies have *low* drag efficiency and stability. *Implication:*
  results on non-circular planforms conflict and depend on set-up. Real practice for small recovery chutes is
  still flat circular/conical.
- **"Experimental Characterization of Drag Coefficient of an UAV Recovery Parachute" (*Journal of Science and
  Technology*, HUST/jst.vn).** Wind tunnel, 3–6 m/s: flat circular canopies had higher Cd than an
  extended-skirt variant. Conical modification reached Cd > 0.90 vs ~0.80 flat, with less oscillation.
  *Implication:* our CFD Cd ≈ 0.81–0.86 (on flat area) for flat-cut canopies is in the right range.

## 2. Porosity, vents and slots (our slits)
- **NASA NTRS 20030064894: AIAA 2003-2129, "Wind Tunnel Testing of Various Disk-Gap-Band Parachutes".** An
  inverse relation between drag and stability; redistributing porosity can regain stability for a small drag
  penalty.
- **NASA TN (NTRS 20010024158): aerodynamic characteristics of flexible porous parachutes.** Drag coefficient
  falls as porosity rises; closing vents reduced stability, enlarging the centre vent improved it.
- **Ring-slot canopy with varying geometric and fabric porosity (wind-tunnel study, ResearchGate; secondary).**
  More geometric porosity: slightly less drag, noticeably more stability.
- **Effective porosity, DTIC AD0729858.** Static stability generally improves with porosity at a small drag cost.
- *Implication for us:* the classic purpose of slots and vents is **stability, not drag**. Our CFD found that the
  short radial cuts **barely open under load** (gaps < 1 mm, porosity ≈ 0–0.8%). They are far below the
  geometric porosity (≈10–20% on ringslot/disk-gap-band canopies) where the literature sees stability
  gains. So our "slits do almost nothing" result is **consistent with prior art**. To get the documented
  stability benefit, slits would have to be cut as real openings (slots with width, or a central vent). That is
  a design-space extension worth naming as future work.

## 3. CFD and fluid-structure interaction (FSI)
- **Takizawa, K., & Tezduyar, T. E. (2012). Computational methods for parachute fluid-structure interactions.
  *Archives of Computational Methods in Engineering, 19*, 125–169. https://doi.org/10.1007/s11831-012-9070-4**
  The reference review: spacecraft ringsail and cluster parachutes, geometric porosity modelled in FSI. Related:
  Takizawa et al. (2011), *Int. J. Numer. Methods Fluids* (parachute clusters); FSI of clusters with modified
  geometric porosity, *Computational Mechanics* (2013).
- **Cao, Y., Nie, S., & Wu, Z.: "Numerical simulation of parachute inflation: A methodological review",
  *Proc. IMechE Part G* (SAGE, doi 10.1177/0954410017705900).**
- **Gao et al. (2016). Fluid-structure interaction analysis of parachute finite mass inflation. *Int. J.
  Aerospace Engineering* (Wiley/Hindawi).**
- *Implication:* full FSI is the state of the art but research-scale. Our approach (quasi-static form-finding
  of the inflated shape + rigid steady RANS) is a recognised simplification: one-way coupling, no flutter or
  breathing. That is why slit opening and swing dynamics are uncertain, and why the real drops are needed.

## 4. Optimisation, surrogates and data-driven design of decelerators
- **Surrogate-based shape optimisation for the stable descent of Mars parachutes (*Aerospace Science and
  Technology*, 2024, ScienceDirect S1270963824003390).** Surrogate + optimiser to maximise drag while
  minimising lateral force: the same **drag-vs-stability two-objective** structure as our NSGA-II study.
- **Optimisation shape design of capsule–supersonic parachute system based on fusion surrogate strategy
  (*Acta Aeronautica et Astronautica Sinica*, 2025, doi 10.7527/S1000-6893.2024.30471).** Fused surrogate
  replaces CFD; multi-objective GA on a disk-gap-band parachute.
- **Optimisation of the reefed parachute using a genetic algorithm (ResearchGate; secondary).** GA minimised
  peak inflation load (reported −43%).
- **Parachute decelerate trajectory optimisation based on GA (IEEE, doc. 5072995).** Canopy area and opening
  time as variables, SQP vs GA.
- *Implication:* CFD → surrogate → GA/NSGA-II is established in the decelerator literature, mainly for
  large or supersonic parachutes. **We found no study that benchmarks several optimisation algorithms against
  each other on parachute design, at small scale, with sensor-measured objectives.** That is the project's
  clearest novelty claim.

## 5. Small-scale drop experiments and on-board sensing
- **NASA NTRS 20070014660: "Parachute dynamics investigations using a sensor package".** Small probes on
  model-rocket parachutes, dropped from an RC aircraft. A **6-DOF IMU + magnetometers were the most useful
  sensors**; pressure, GPS and camera add-ons had little success.
- **Apogee Components technical notes (Peak of Flight newsletters 449, 621; *Insights: Descent Rate*).**
  Hobby practice: Cd from timed drops or video with a scale. Error from the opening phase.
- **NOVA (PBS) classroom activity.** Timed drops from 4.5 m. ~2 m/s for an 18 cm canopy (no sensing).
- *Implication:* IMU-centred measurement matches what NASA found most useful. Our addition is **RGB-D +
  IMU fusion with LED clock sync and a pipeline validated against simulator truth (0.03 m/s)**, which we did
  not find for small drops. Our 4 m drop is short: the payload does not reach terminal speed (consistent with
  the "opening phase" error noted by Apogee). That is why we compare designs on *pre-impact speed*, not
  terminal speed.

## 6. Comparing GA, SA, PSO and BO
- **Wolpert, D. H., & Macready, W. G. (1997). No free lunch theorems for optimization. *IEEE Trans.
  Evolutionary Computation, 1*(1), 67–82. https://doi.org/10.1109/4235.585893.** Averaged over all problems no
  algorithm wins. Rankings are problem-specific, which is the reason to benchmark on *our* problem.
- **Jaw et al. (2017). A comparison of SA, GA and PSO in optimal first-order design of indoor TLS networks.
  *ISPRS Annals IV-2/W4*, 75.** PSO ≈ GA; SA did not reliably reach the optimum in the iteration limit.
- **Conceptual comparison of population-based metaheuristics for engineering problems (*PMC4383342*).**
  Tabulated results on welded beam / pressure vessel benchmarks.
- *Implication:* conflicting rankings across problems are expected (no free lunch). Our benchmark adds
  Bayesian optimisation and a gradient method under a **fixed evaluation budget with noisy, occasionally invalid
  sensor-measured objectives**, a setting the cited comparisons do not cover.

## What this means for our findings
| Our finding | Prior art says | Verdict |
|---|---|---|
| Round canopies give the most drag (CFD, ~10% spread) | flat outline barely matters (disc ≈ square plate); cupping adds ~20% drag; conical/circular standard in practice | consistent: the effect is through inflated cup depth |
| Short radial slits barely open (< 1 mm) and slightly reduce stability | slots/vents add stability only at ~10–20% geometric porosity, with a small drag cost | consistent; our slits are far below the effective porosity range |
| All canopies statically unstable (Cm_alpha > 0) | non-porous flat circular canopies oscillate; porosity is the usual fix | consistent |
| Multi-objective drag vs stability | Mars-parachute surrogate studies optimise exactly this pair | established approach |
| Optimiser comparison | no free lunch; no parachute-specific multi-optimiser benchmark found | our contribution |

## Limitations of this brief
Quick mode: one search pass per theme; abstracts or secondary pages were used for several entries (marked
"secondary"). Handbook numbers (Knacke, Hoerner) were seen through secondary sources only. Chinese-language
surrogate papers were seen at abstract level. Before the final report, check the starred numbers in the
originals (Knacke via DTIC ADA247666).

*AI disclosure: this brief was compiled with AI assistance (web search + synthesis). References were checked for
existence and bibliographic details; claims marked secondary were not checked against the full text.*
