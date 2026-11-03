"""Add bottom-right source lines and glanceable notes to the user's edited deck (in place, other edits kept)."""
import re
import sys
import zipfile
from xml.sax.saxutils import escape

SRC, OUT = sys.argv[1], sys.argv[2]

SOURCES = {
    2: "Drop simulator: MuJoCo (Todorov et al., 2012)",
    3: "Form-finding: dynamic relaxation (Day, 1965)",
    5: "VAE: Kingma & Welling (2014)",
    6: "Reference Cd: Hoerner, Fluid-Dynamic Drag (1965) · CFD: OpenFOAM v2406, k-ω SST (Menter, 1994)",
    10: "CFD: OpenFOAM v2406, k-ω SST turbulence model (Menter, 1994)",
    11: "GA: pymoo (Blank & Deb, 2020)",
    15: "GA, multi-objective GA: pymoo (Blank & Deb, 2020) · GP: scikit-learn (Pedregosa et al., 2011)",
    16: "NSGA-II: Deb et al. (2002)",
}

NOTES = {
1: """# SPEAKER 1  ·  6 s
## SAY
- Hi, we're Prabal, Pranav and Walter.
- Can a data-driven search beat a simple hole in the middle?
## IF ASKED
- Project questions? → Which canopy lands slowest with fixed plastic and OK stability. Which course methods find good designs best.""",
2: """# SPEAKER 1  ·  25 s  ·  CLICK VIDEO
## SAY
- This is a simulated drop.
- Same 250 cm² of plastic, any 2D shape.
- 4 m drop, 6 lines.
- Goal: lowest landing speed, plus pitch stability.
- Free fall: 8.9 m/s. Best so far: 6.3.
- Payload mass is assumed until we weigh it.
## IF ASKED
- Why landing speed? → Measured the same way in simulated and real drops.
- Why 250 cm²? → Same material for every design, so it's fair.
- Why 4 m? → At 2.5 m no design stood out, in all 27 assumption sets.
- 8.9 m/s? → Free fall with no drag: √(2·g·h).
- 6.3 m/s? → The vent's CFD estimate, not a measurement. 95 g payload and 3 g canopy assumed.""",
3: """# SPEAKER 1  ·  15 s
## SAY
- We started with slits.
- In our model they opened under 1 mm, so almost no effect.
- So we changed the encoding: 3 → 7 → 9 variables.
- Changing only the centre weight opens a hole.
- 78% of free-form shapes can be cut.
## IF ASKED
- 3 variables? → Outline q (2 = circle), slit length, slit position.
- 7 variables? → Vent size, side-hole area, count, distance, stretch, shape, rotation. Outline q still applies.
- 9 variables? → 61 Gaussian bumps on a hill. 6-fold symmetry groups them into 9 weights.
- Do slits fail for real? → That's our model's result, not tested on real canopies.
- Which weights matter? → Sobol: the outer edge weights. That's the surrogate, not CFD.""",
4: """# SPEAKER 1  ·  20 s  ·  CLICK VIDEO
## SAY
- Think of a sandcastle.
- Smooth hill, 61 spots, grouped into 9.
- Each variable adds or digs sand at its group.
- Raise the water until exactly 250 cm² sticks out.
- Above the water is plastic. The rest is cut away.
- New numbers, new shape, same plastic.
## IF ASKED
- The math? → height = 1 − (r/R)² + Σ w × Gaussian. Plastic where height > t.
- The water level? → Found by bisection for every design, so area is never a variable.
- Why 9, not 61? → Symmetry matches the 6 lines and shrinks the search.
- Why this encoding? → Outline and holes come from one field. We never place holes by hand.
- Is it novel? → No. Standard level-set / RBF shape method plus symmetry linking.
- Which designs? → Real CFD designs, free56 then free07.""",
5: """# SPEAKER 1  ·  20 s  ·  THEN HAND TO SPEAKER 2
## SAY
- PCA, autoencoder and VAE on 1,883 shapes.
- Scored on shapes they never trained on.
- IoU = overlap ÷ union.
- At 9 dimensions: autoencoder 0.97, PCA 0.94.
- We still search the 9 weights directly.
## IF ASKED
- Why three methods? → PCA = linear baseline. Autoencoder = nonlinear. VAE also makes new shapes.
- The data? → 48 × 48 masks, held-out test shapes.
- Why not search with the VAE? → Only 66% of its shapes were one piece.
- Does this prove 9 weights are best? → No. Latent codes and field weights are separate.""",
6: """# SPEAKER 2  ·  30 s  ·  CLICK VIDEO
## SAY
- This is the whole workflow, left to right.
- Latin hypercube sampling picks training shapes.
- Each is inflated, then CFD at 0° and 10°.
- CFD is too slow for every candidate, so it trains a Gaussian process surrogate.
- The optimizer searches the surrogate. Winners get fresh CFD.
- Camera + IMU: same code for simulated and real drops.
- Disc and cup are within 7% of published drag.
## IF ASKED
- Why a surrogate? → One CFD run is 30+ min. 200 evals × 10 runs per method is impossible.
- CFD setup? → OpenFOAM, k-ω SST, 7 m/s.
- How does search judge a shape? → GP score from shape features, plus cut check and inflation classifier. It never sees physics.
- Stability? → Cm_alpha = moment slope from 0° and 10°. Positive = a tilt grows.
- Limits? → Shape from uniform pressure, no CFD feedback. Disc +5.6%, cup +6.8%.
- Reference values? → Hoerner, Fluid-Dynamic Drag (1965).""",
7: """# SPEAKER 2  ·  15 s
## SAY
- Here's the scale of the work.
- 130 CFD runs → 45 converged designs.
- 780 shapes scanned for inflation.
- 1,883 shapes for dimensionality reduction.
- 200 evaluations × 10 runs per method.
- 5 winners re-checked with fresh CFD.
## IF ASKED
- 130 vs 45? → 51 inflated stably, 6 didn't converge. Each design needs 2 angles.
- Inflation classifier? → Random forest, 77% accuracy. Our addition, not a course method.
- Real drops? → None yet. Everything here is simulation.""",
8: """# SPEAKER 2  ·  18 s
## SAY
- All four use exactly 250 cm².
- Central vent: 6.31 m/s.
- 0.14 slower than plain, 54% less pitch instability.
- Not yet self-righting.
- Big hole is worst: 7.20.
- CFD estimates, not measurements.
## IF ASKED
- What is 12%? → Hole = 12% of plastic area (10.7% of the outline).
- Numbers? → Drag area 243.6 vs 219.5 cm². Cm_alpha +2.25 vs +4.89 (×1e-3 per °).
- Why does a hole help? → Bigger drag area, less unstable. Venting is the likely reason, untested.
- Self-righting designs? → Only 4 of 45. The best of those lands at 6.91 m/s.""",
9: """# SPEAKER 2  ·  12 s
## SAY
- Each dot is one CFD design.
- Best results around 10% open.
- Past 30% open, drag falls and speed climbs.
## IF ASKED
- No-hole designs? → 19 at 0% open, median 6.50 m/s.
- Is 10% exact? → No. Only 13 designs between 1–15%, median 6.43. A region, not an optimum.""",
10: """# SPEAKER 2  ·  10 s  ·  THEN HAND TO SPEAKER 3
## SAY
- Left: big opening, air runs straight through.
- Right: tilted 10°, the wake goes lopsided.
- That's why stability is hard.
## IF ASKED
- Left design? → free03, ~26% open, self-righting, 6.91 m/s.
- Right image? → Older slit canopy, coarse mesh. Shows the idea only.
- Why not show the vent? → Its flow fields were lost when the rented machines shut down. Forces were saved.""",
11: """# SPEAKER 3  ·  30 s  ·  CLICK VIDEO
## SAY
- The GA evolves a population of designs.
- The surrogate scores each one's fitness.
- Grey = rejected: can't be cut or won't inflate.
- Budget: 200 evaluations.
- The best designs then get fresh CFD.
## IF ASKED
- Why a GA? → Handles 9 variables, needs no gradients.
- How? → 20 designs per generation. Keep the best, crossover, mutation. This is a real run, 10 generations.
- Fitness? → Lowest predicted speed + 0.03 m/s test noise. Rejected = marked penalty.
- Speed on screen? → A noisy surrogate score, not a real speed.""",
12: """# SPEAKER 3  ·  6 s
## SAY
- No rule told it to do this.
## IF ASKED
- Did it really invent it? → It learned from CFD data that included holed designs. Open area is one of its features.""",
13: """# SPEAKER 3  ·  15 s
## SAY
- This is the check.
- GA winners predicted ~6.27 m/s.
- Fresh CFD: 0.06 to 0.17 slower.
- Optimise on a model and you find its mistakes.
- All five winners inflated stably.
## IF ASKED
- All five in CFD? → 6.33, 6.36, 6.41, 6.41, 6.44. The 3 GA ones are shown.
- The other two? → Other methods, predicted within 0.01, but both ~6.40. Error grew with how hard the search pushed. Only 5 designs, so a clue.
- Why optimistic? → Only ~40 training designs. Search hunts where the errors look good.""",
14: """# SPEAKER 3  ·  15 s
## SAY
- Best search winner: 6.33 in CFD.
- Hand-made vent: 6.31.
- Gap of 0.02, no uncertainty yet.
- So the vent has the lowest checked estimate.
- The search got close, starting from random shapes.
## DON'T SAY
- The vent is clearly better.
## IF ASKED
- Stability? → Cm_alpha +2.53 winner vs +2.25 vent (×1e-3 per °). Neither self-righting.""",
15: """# SPEAKER 3  ·  20 s
## SAY
- Each method: 200 evaluations × 10 runs.
- Score = best surrogate speed with noise. It ranks methods, not real speeds.
- Median, and IQR = spread across runs.
- GA and PSO led.
- Tabu trailed, with the widest spread.
## IF ASKED (reasons are likely, not tested)
- Why so many methods? → Comparing them is the project.
- Why none beat the vent? → All searched the surrogate. The surrogate is the limit.
- Tabu 6.475? → Fixed steps, poor fit for 9 continuous variables.
- Random 6.312? → Many designs score well on the surrogate.
- SA 6.303? → One design at a time. 200 evals is few in 9-D.
- BO 6.293? → Noise and rejected designs hurt its model. Untuned.
- Multi-objective GA 6.288? → Also optimises stability, so not a loser.
- GA 6.260, PSO 6.271? → Population-based, cope better with noise.
- What is PSO? → A swarm of designs; each moves toward its own best and the swarm's best.
- Is GA best in general? → No. One surrogate, one budget, our settings.""",
16: """# SPEAKER 3  ·  20 s  ·  END
## SAY
- Same goal: lowest speed, plus stability.
- 1. Feed CFD checks back with Bayesian optimization.
- 2. Multi-objective GA (NSGA-II): Pareto front, speed vs stability.
- 3. Real drops decide.
- Vent's 0.14 gain ≈ what 3 repeats can detect, so we need more repeats.
- Thank you. Questions?
## IF ASKED
- Why these steps? → More CFD = less surrogate error. BO picks the next runs. Speed and stability conflict.
- 0.139 m/s? → 4 standard errors, 0.06 m/s noise per drop, 3 repeats. Noise is assumed.
- Still needed? → Weigh payload, IMU wiring, RealSense model, recorder, hole stencils.
- Is NSGA-II in the course? → Not by name. It's the multi-objective GA (week 4).""",
}


def run(text, sz, bold=False, color=None):
    fill = f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>' if color else ""
    return (f'<a:r><a:rPr b="{int(bold)}" lang="en-US" sz="{sz}" spc="-1" strike="noStrike">{fill}'
            f'<a:latin typeface="Arial"/></a:rPr><a:t>{escape(text)}</a:t></a:r>')


def para(runs, before=0):
    sp = f'<a:spcBef><a:spcPts val="{before}"/></a:spcBef>' if before else ""
    return f'<a:p><a:pPr><a:lnSpc><a:spcPct val="100000"/></a:lnSpc>{sp}<a:buNone/></a:pPr>{"".join(runs)}</a:p>'


def notes_xml(src):
    out = []
    for line in src.strip().splitlines():
        if line.startswith("# "):
            out.append(para([run(line[2:], 2400, True)]))
        elif line.startswith("## "):
            out.append(para([run(line[3:], 1600, True, "C0504D")], before=900))
        else:
            body = line[2:]
            if " → " in body:
                q, a = body.split(" → ", 1)
                out.append(para([run("• " + q + "  ", 1700, True), run(a, 1700)], before=300))
            else:
                out.append(para([run("• " + body, 2200)], before=300))
    return "".join(out)


def source_sp(text, sid):
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="Source"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            '<p:spPr><a:xfrm><a:off x="4389120" y="6355080"/><a:ext cx="6766560" cy="273960"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln w="0"><a:noFill/></a:ln></p:spPr>'
            '<p:txBody><a:bodyPr lIns="0" rIns="0" tIns="0" bIns="0" anchor="t" wrap="square"><a:noAutofit/></a:bodyPr>'
            '<a:p><a:pPr algn="r"><a:lnSpc><a:spcPct val="100000"/></a:lnSpc><a:buNone/></a:pPr>'
            '<a:r><a:rPr b="0" i="1" lang="en-US" sz="1050" spc="-1" strike="noStrike"><a:solidFill><a:srgbClr val="b3a7be"/></a:solidFill>'
            f'<a:latin typeface="Calibri"/></a:rPr><a:t>{escape(text)}</a:t></a:r></a:p></p:txBody></p:sp>')


zin = zipfile.ZipFile(SRC)
# slide order from presentation.xml
pres = zin.read("ppt/presentation.xml").decode()
prels = zin.read("ppt/_rels/presentation.xml.rels").decode()
rid2t = dict((m.group(1), m.group(2)) for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', prels))
rid2t.update((m.group(2), m.group(1)) for m in re.finditer(r'Target="([^"]+)"[^>]*Id="(rId\d+)"', prels))
order = ["ppt/" + rid2t[r] for r in re.findall(r'<p:sldId [^>]*r:id="(rId\d+)"', pres)]
patch = {}
for n, path in enumerate(order, 1):
    x = zin.read(path).decode()
    if n in SOURCES:
        x = re.sub(r'<p:sp><p:nvSpPr><p:cNvPr id="\d+" name="Source"/>.*?</p:sp>', "", x, flags=re.S)
        sid = max(int(v) for v in re.findall(r'<p:cNvPr id="(\d+)"', x)) + 1
        i = x.rfind("</p:spTree>")
        x = x[:i] + source_sp(SOURCES[n], sid) + x[i:]
        patch[path] = x
    rels = zin.read(path.replace("slides/", "slides/_rels/") + ".rels").decode()
    nf = re.search(r'Target="\.\./notesSlides/(notesSlide\d+\.xml)"', rels)
    if nf and n in NOTES:
        npath = "ppt/notesSlides/" + nf.group(1)
        nx = zin.read(npath).decode()
        m = re.search(r'(<p:ph type="body"[^>]*/>.*?<p:txBody>)(.*?)(</p:txBody>)', nx, re.S)
        head = re.match(r'((?:<a:bodyPr[^>]*/>|<a:bodyPr[^>]*>.*?</a:bodyPr>)(?:<a:lstStyle/>|<a:lstStyle>.*?</a:lstStyle>)?)', m.group(2), re.S)
        nx = nx[:m.start(2)] + head.group(1) + notes_xml(NOTES[n]) + nx[m.end(2):]
        patch[npath] = nx
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zout:
    for it in zin.infolist():
        data = patch[it.filename].encode() if it.filename in patch else zin.read(it.filename)
        zout.writestr(it, data, compress_type=zipfile.ZIP_STORED if it.filename == "mimetype" else zipfile.ZIP_DEFLATED)
print("slides", len(order), "patched", len(patch))
