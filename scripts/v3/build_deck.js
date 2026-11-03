// Nov 3 mid-way deck. Needs pptxgenjs on NODE_PATH; media comes from deck_media.py and deck_assets.py.
//   NODE_PATH=<dir>/node_modules node scripts/v3/build_deck.js <pptx skill dir>
const path = require("path"), fs = require("fs");
const pptxgen = require("pptxgenjs");
const { applyTheme } = require(path.join(process.argv[2], "scripts/apply_theme.js"));
const DIR = path.join(__dirname, "../../presentation/midway_2026-11-03");
const M = (f) => path.join(DIR, "media", f);
const b64 = (f) => "image/png;base64," + fs.readFileSync(M(f)).toString("base64");

const BG = "15091F", PANEL = "261633", ORANGE = "FF8A3D", LIGHT = "E9DDF2", MUTED = "B3A7BE", GRID = "3A3044", LILAC = "B58BD6";
const THEME = { name: "Canopy Night", headFontFace: "Cambria", bodyFontFace: "Calibri", colors: {
  dk1: BG, lt1: "FFFFFF", dk2: PANEL, lt2: LIGHT,
  accent1: ORANGE, accent2: LILAC, accent3: MUTED, accent4: "7CF5FF", accent5: "6E5A80", accent6: GRID,
  hlink: ORANGE, folHlink: LILAC } };

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  pres.title = "Parachute design: mid-way presentation";

  pres.defineSlideMaster({ title: "TITLE", background: { color: BG },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.7, y: 1.3, w: 5.7, h: 2.75, fontSize: 46, bold: true, color: "FFFFFF", align: "left", valign: "bottom", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.7, y: 4.3, w: 5.5, h: 1.1, fontSize: 18, color: LIGHT, align: "left", valign: "top", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "names", type: "body", x: 0.7, y: 5.6, w: 5.8, h: 0.8, fontSize: 16, color: LIGHT, align: "left", valign: "top", margin: 0 }, text: "Add team names" } },
    ] });
  pres.defineSlideMaster({ title: "CONTENT", background: { color: BG }, slideNumber: { x: 12.3, y: 6.98, w: 0.5, h: 0.3, fontSize: 11, color: MUTED, align: "right" },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.4, w: 12.1, h: 1.1, fontSize: 32, bold: true, color: "FFFFFF", align: "left", valign: "top", margin: 0 }, text: "" } },
    ] });

  const txt = (s, t, o) => s.addText(t, { isTextBox: true, margin: 0, fontSize: 16, color: LIGHT, valign: "top", ...o });
  const cap = (s, t, x, y, w, h) => txt(s, t, { x, y, w, h: h || 0.3, fontSize: 12, color: MUTED });
  const stat = (s, big, small, x, y, w, col) => {
    txt(s, big, { x, y, w, h: 0.62, fontSize: 36, bold: true, color: col || ORANGE });
    txt(s, small, { x, y: y + 0.64, w, h: 0.55, fontSize: 15 });
  };
  const chartText = { catAxisLabelColor: LIGHT, valAxisLabelColor: LIGHT, catAxisLabelFontSize: 14, valAxisLabelFontSize: 12,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catGridLine: { style: "none" }, catAxisLineColor: GRID, valAxisLineColor: GRID };
  const page = () => pres.addSlide({ masterName: "CONTENT" });

  const PENDING = "Simulation estimates; physical validation pending";
  const tag = (s) => txt(s, PENDING, { x: 0.6, y: 6.95, w: 8, h: 0.3, fontSize: 13, italic: true, color: MUTED });
  // poster under the video, so the slide is not blank in a PDF or if playback fails
  const video = (s, file, cover, x, y, w, h) => {
    s.addImage({ path: M(cover), x, y, w, h, altText: "Still from the video" });
    s.addMedia({ type: "video", path: M(file), cover: b64(cover), x, y, w, h });
  };
  const chain = (s, steps, x0, y, w, h, gap, fs, hot) => steps.forEach((t, i) => s.addText(t, { shape: pres.shapes.PENTAGON, x: x0 + i * (w + gap), y, w, h,
    fill: { color: hot.includes(i) ? ORANGE : PANEL }, color: hot.includes(i) ? BG : LIGHT, bold: hot.includes(i), fontSize: fs, align: "center", valign: "middle", margin: 3 }));

  const cell = (t, o) => ({ text: t, options: { fontSize: 15, color: LIGHT, fill: { color: BG }, border: { type: "none" }, ...o } });
  const hdr = (t, a) => cell(t, { bold: true, color: "FFFFFF", align: a });
  const cell0 = cell, hdr0 = hdr;

  // Title
  let s = pres.addSlide({ masterName: "TITLE" });
  s.addText("Can a data-driven search beat a hole in the middle?", { placeholder: "title" });
  s.addText("Comparative evaluation of data-driven design methods for parachute shape and slit optimization", { placeholder: "body" });
  s.addText("Prabal Khare (pk3391), Pranav, Walter", { placeholder: "names" });
  s.addImage({ path: M("inflate_final.png"), x: 6.6, y: 0.35, w: 6.73, h: 6.73, altText: "Inflated canopy with a central vent and suspension lines" });
  txt(s, "ROB-GY 7863B, NYU Tandon", { x: 0.7, y: 6.45, w: 5.8, h: 0.3, fontSize: 14, color: MUTED });
  s.addNotes("6 seconds. Introduce the team and ask the question. @@ PROJECT QUESTIONS: (1) Which canopy lands slowest, with acceptable stability, using fixed plastic? (2) Which course methods find good designs most efficiently and reliably? @@ TEAM: Prabal Khare, Pranav and Walter.");

  // Problem and setup
  s = page();
  s.addText("250 cm² of plastic. How slowly can it land?", { placeholder: "title" });
  video(s, "camera_drop_slowmo.mp4", "slowmo_cover.png", 0.6, 1.5, 8.3, 3.4);
  txt(s, "Simulated drop, slow motion", { x: 0.6, y: 4.95, w: 8.3, h: 0.3, fontSize: 14, color: MUTED });
  stat(s, "8.9 m/s", "free fall from 4 m", 9.3, 1.5, 3.4);
  stat(s, "6.3 m/s", "best estimate so far", 9.3, 3.1, 3.4, LILAC);
  txt(s, "Objectives: lowest landing speed, plus pitch stability", { x: 0.6, y: 5.4, w: 12.1, h: 0.5, fontSize: 24, bold: true, color: "FFFFFF" });
  txt(s, "Setup: 250 cm² of plastic in any 2D shape, 4 m drop, 6 lines, 95 g payload (assumed)", { x: 0.6, y: 6.0, w: 12.1, h: 0.4, fontSize: 18 });
  tag(s);
  s.addNotes("25 seconds. Click the video. This is a simulated drop. Same plastic every time, any 2D shape, dropped from 4 m on 6 lines. We minimise speed just before impact and track pitch stability as the second objective. Free fall is 8.9 m/s. Payload mass is assumed until weighed. @@ WHY LANDING SPEED: it is the speed just before impact, and it can be measured the same way in simulated and real drops. @@ WHY 250 CM²: every design uses the same material, so the comparison is fair. @@ WHY 4 M: at 2.5 m our feasibility sweep could not separate designs in any of 27 assumption sets. @@ IF ASKED, 8.9 M/S: free fall from 4 m with no drag, the square root of 2 × g × h. @@ IF ASKED, 6.3 M/S: this is the 12% vent's CFD estimate, not a measurement. The speed uses an assumed 95 g payload and 3 g canopy.");

  // Slits fail -> encodings
  s = page();
  s.addText("Slits barely opened in our model", { placeholder: "title" });
  s.addImage({ path: M("slit_3d.png"), x: 0.6, y: 1.65, w: 3.0, h: 2.52, altText: "Inflated canopy with radial slits" });
  txt(s, "< 1 mm", { x: 0.6, y: 4.35, w: 3.0, h: 0.75, fontSize: 40, bold: true, color: ORANGE });
  txt(s, "slit opening, 36 form-found designs", { x: 0.6, y: 5.1, w: 3.0, h: 0.6, fontSize: 15 });
  [["enc_param.png", "3 variables", "Outline, slit length, slit position"], ["enc_cut.png", "7 variables", "Vent size; side hole count, size, place, shape"]].forEach(([img, k, d], i) => {
    const x = 3.95 + i * 2.2;
    s.addImage({ path: M(img), x, y: 1.7, w: 1.9, h: 1.9, altText: k + " encoding example" });
    txt(s, k, { x, y: 3.85, w: 2.0, h: 0.45, fontSize: 22, bold: true, color: "FFFFFF", fontFace: "Cambria" });
    txt(s, d, { x, y: 4.35, w: 2.0, h: 1.2, fontSize: 15 });
  });
  s.addImage({ path: M("weight_0.png"), x: 8.45, y: 1.7, w: 1.9, h: 1.9, altText: "Free-form canopy with all weights at zero" });
  s.addImage({ path: M("weight_hole.png"), x: 10.8, y: 1.7, w: 1.9, h: 1.9, altText: "Free-form canopy with a central hole" });
  txt(s, "→", { x: 10.3, y: 2.3, w: 0.5, h: 0.6, fontSize: 28, bold: true, color: ORANGE, align: "center" });
  txt(s, "9 variables", { x: 8.45, y: 3.85, w: 4.2, h: 0.45, fontSize: 22, bold: true, color: ORANGE, fontFace: "Cambria" });
  txt(s, "Heights of 61 smooth bumps, in 9 symmetric groups. Centre weight 0 → −1.6: a hole opens.", { x: 8.45, y: 4.35, w: 4.25, h: 1.2, fontSize: 15 });
  txt(s, "Every design must be cuttable: 78% of free-form samples pass.", { x: 3.95, y: 5.85, w: 8.75, h: 0.4, fontSize: 18, color: "FFFFFF" });
  s.addNotes("15 seconds. We started with slits. Form-finding on 36 designs showed under 1 mm of opening in our model, so they did almost nothing. So we changed the encoding, which is how design variables become a shape. 3 variables set the outline and slits, 7 set the holes, and 9 set the heights of smooth bumps. Changing just the centre weight opens a hole. 78% of free-form samples can be cut. @@ 3 VARIABLES: outline shape q (2 is a circle, higher is squarer), slit length, slit position. @@ 7 VARIABLES: vent size, total side hole area, hole count, distance from centre, stretch, hole shape, rotation. The outline q still applies, so 7 means the hole settings. @@ 9 VARIABLES: a smooth hill plus 61 Gaussian bumps. Positive weights add material and negative weights dig it away. Plastic is everything above a threshold, set so the area is exactly 250 cm². Six-fold symmetry groups the 61 bumps into 9 weights, matching the 6 lines. @@ IF ASKED, WHY SLITS FAILED: form-finding showed under 1 mm of opening, so almost no air passes. That result comes from our model, not from real canopies. @@ IF ASKED, WHICH WEIGHTS MATTER: Sobol analysis says the surrogate is most sensitive to the outer edge weights. That describes the surrogate, not CFD directly.");

  // How the 9 variables work
  s = page();
  s.addText("How 9 variables make a canopy", { placeholder: "title" });
  video(s, "sand.mp4", "sand_cover.png", 1.85, 1.35, 9.6, 5.4);
  s.addNotes("20 seconds. Click the video. Think of a sandcastle. We start with a smooth hill and mark 61 spots. Symmetry groups them into 9, one for each variable. Each variable adds sand or digs a dip at its group of spots. Then we raise the water until exactly 250 cm² sticks out. What's above the water is plastic, and the rest is cut away. New numbers give a new shape, always with the same plastic. @@ THE MATH: height = 1 - (r/R)² plus the sum of w × a Gaussian bump. Plastic is where height is above the level t. @@ THE WATER LINE: the level is solved by bisection for every design, so area is never a design variable. @@ WHY 9 AND NOT 61: 6-fold symmetry with mirroring matches the 6 lines and shrinks the search space. @@ WHY THIS ENCODING: outlines and holes both appear from one field, so we never prescribe where a hole goes. @@ IF ASKED, WHICH DESIGNS: the video uses real designs from our CFD set, free56 then free07. The sand and water are an analogy for a height field and threshold.");

  // Dimensionality reduction
  s = page();
  s.addText("Dimensionality reduction on sampled shapes", { placeholder: "title" });
  const ks = ["2", "4", "6", "9", "16"];
  s.addChart(pres.charts.LINE, [
    { name: "PCA", labels: ks, values: [0.827, 0.893, 0.914, 0.936, 0.958] },
    { name: "Autoencoder", labels: ks, values: [0.893, 0.939, 0.966, 0.971, 0.972] },
    { name: "VAE", labels: ks, values: [0.897, 0.939, 0.961, 0.966, 0.959] }],
    { x: 0.6, y: 1.4, w: 6.3, h: 5.1, chartColors: [MUTED, ORANGE, LILAC], lineSize: 3, lineDataSymbolSize: 8,
      showTitle: false, showLegend: true, legendPos: "b", legendFontSize: 14, legendFontFace: "+mn-lt", legendColor: LIGHT,
      showCatAxisTitle: true, catAxisTitle: "Latent space size", catAxisTitleFontSize: 14, catAxisTitleColor: LIGHT, catAxisTitleFontFace: "+mn-lt",
      showValAxisTitle: true, valAxisTitle: "Held-out reconstruction IoU", valAxisTitleFontSize: 14, valAxisTitleColor: LIGHT, valAxisTitleFontFace: "+mn-lt",
      valAxisMinVal: 0.8, valAxisMaxVal: 1.0, valAxisMajorUnit: 0.05, valAxisLabelFormatCode: "0.00", valGridLine: { color: GRID, size: 0.75 }, ...chartText });
  s.addImage({ path: M("vae_samples.png"), x: 7.3, y: 1.5, w: 5.4, h: 2.03, altText: "Canopy shapes generated by the VAE" });
  txt(s, "Shapes the VAE invented", { x: 7.3, y: 3.6, w: 5.4, h: 0.35, fontSize: 18, color: "FFFFFF" });
  stat(s, "0.97", "autoencoder IoU at 9-D, on shapes it never trained on", 7.3, 4.15, 5.4);
  txt(s, "IoU: overlap ÷ union of two shapes. 1.0 is a perfect match.", { x: 7.3, y: 5.5, w: 5.4, h: 0.65, fontSize: 15, color: MUTED });
  s.addNotes("20 seconds. PCA, autoencoder and VAE on 1,883 sampled canopy masks, scored on held-out shapes. IoU is overlap divided by union. At 9 latent dimensions the autoencoder reaches 0.97 and PCA 0.94. These latent codes are a separate representation from our 9 field weights, and this does not prove those weights are the best choice. We search the weights directly for now. 66% of VAE shapes are one piece, so the VAE stays a generator to test later. @@ WHY THREE METHODS: PCA is the linear baseline. The autoencoder is nonlinear, so it can compress curved shape patterns. The VAE also generates new shapes. @@ DATA: 1,883 sampled canopy shapes as 48 × 48 masks, scored on held-out shapes. @@ IF ASKED, WHY NOT SEARCH WITH THE VAE: at 9 dimensions, only 66% of its generated shapes were one piece, so it stays a generator to test later. @@ IF ASKED, DOES THIS PROVE 9 WEIGHTS ARE OPTIMAL: no. Latent codes and field weights are separate representations.");

  // Workflow, data capture and validation
  s = page();
  s.addText("CFD trains a surrogate model for design search", { placeholder: "title" });
  chain(s, ["Encoding", "Cuttable design", "DOE + CFD training data", "Surrogate model (GP)", "GA, PSO, BO search", "Fresh CFD check"], 0.6, 1.4, 1.98, 0.95, 0.05, 14, [3, 5]);
  video(s, "inflate.mp4", "inflate_cover.png", 0.6, 2.6, 3.9, 3.9);
  txt(s, "Form-finding: flat pattern to inflated shape", { x: 0.6, y: 6.53, w: 4.6, h: 0.3, fontSize: 13, color: MUTED });
  txt(s, "Measurement: simulated and future real drops", { x: 4.9, y: 2.6, w: 7.8, h: 0.35, fontSize: 17, bold: true, color: "FFFFFF" });
  chain(s, ["Camera + IMU", "Pose filter", "Landing speed"], 4.9, 3.05, 2.55, 0.8, 0.05, 15, []);
  txt(s, "CFD check on reference shapes", { x: 4.9, y: 4.2, w: 7.8, h: 0.35, fontSize: 17, bold: true, color: "FFFFFF" });
  stat(s, "1.235", "disc Cd, reference 1.17", 4.9, 4.65, 3.6);
  stat(s, "1.516", "cup Cd, reference 1.42", 8.7, 4.65, 3.6, LILAC);
  s.addNotes("30 seconds. Click the video. This is the whole workflow. Latin hypercube sampling picks the training shapes. Each is inflated, then run through OpenFOAM at 0 and 10 degrees. CFD is too slow to run for every candidate, so those runs train a Gaussian process surrogate model. The optimizer searches on the surrogate, and only selected winners get a fresh CFD check. Underneath, camera and IMU data go through the same code for simulated and future real drops. Validation: disc and cup are within 7% of published drag values. Real drops are the check still to come. @@ WHY A SURROGATE: one CFD run takes 30 minutes or more, so 200 evaluations for every method and run is not practical. @@ STEPS: Latin hypercube sampling spreads training designs evenly. The fabrication check removes shapes we cannot cut. Form-finding gives the inflated shape. OpenFOAM with k-omega SST gives drag and pitching moment at 7 m/s. @@ NUMBERS: 130 CFD runs, 51 stable designs, 45 converged. An inflation scan of 780 shapes found 64% stable, and that trained a classifier with 77% accuracy. @@ IF ASKED, STABILITY: Cm_alpha is the slope of pitching moment with angle, estimated from 0 and 10 degrees only. Positive means a tilt grows. @@ IF ASKED, LIMITS: the shape comes from uniform pressure and CFD runs on that frozen shape, so there is no feedback. Disc and cup both read high, by 5.6% and 6.8%.");

  // What we ran
  s = page();
  s.addText("What we ran so far", { placeholder: "title" });
  [["130", "CFD runs on form-found canopies"], ["45", "converged designs with both angles"], ["780", "shapes in the inflation scan, 64% stable"],
   ["1,883", "sampled shapes for dimensionality reduction"], ["200 × 10", "evaluations × runs for each search method"], ["5", "search winners re-checked with fresh CFD"]].forEach(([b, t], i) => {
    const x = 0.6 + (i % 3) * 4.1, y = 1.7 + Math.floor(i / 3) * 2.3;
    txt(s, b, { x, y, w: 3.8, h: 0.9, fontSize: 48, bold: true, color: i % 3 === 1 ? LILAC : ORANGE });
    txt(s, t, { x, y: y + 0.95, w: 3.7, h: 0.75, fontSize: 18 });
  });
  s.addNotes("15 seconds. Here's the scale of the work so far. 130 CFD runs gave 45 converged designs. We scanned 780 shapes for stable inflation, used 1,883 for dimensionality reduction, and gave each search method 200 evaluations over 10 runs. Then 5 winners got fresh CFD. @@ IF ASKED, 130 AGAINST 45: 51 designs inflated stably and 6 of those did not converge, so we excluded them. Each design needs two angles. @@ IF ASKED, INFLATION CLASSIFIER: the 780-shape scan trained a random forest classifier with 77% accuracy, which screens out shapes likely to flutter. It is our addition, not a course method. @@ These are all simulation runs. No real-drop data is included.");

  // Vent result
  const four = [["quiz_free07.png", "30% open", "6.40"], ["quiz_base_q2.8.png", "Plain canopy", "6.45"], ["quiz_vent12.png", "12% vent", "6.31"], ["quiz_free52.png", "49% open", "7.20"]];
  s = page();
  s.addText("A central vent gave the lowest estimate", { placeholder: "title" });
  four.forEach(([img, l, v], i) => {
    const x = 0.6 + i * 3.08, win = i === 2;
    s.addImage({ path: M(img), x: x + 0.1, y: 1.6, w: 2.7, h: 2.7, altText: l });
    txt(s, l, { x, y: 4.45, w: 2.9, h: 0.45, fontSize: 20, bold: true, align: "center", color: win ? ORANGE : "FFFFFF" });
    txt(s, v + " m/s", { x, y: 4.95, w: 2.9, h: 0.65, fontSize: 32, bold: true, align: "center", color: win ? ORANGE : MUTED });
  });
  txt(s, "Vent against plain: 0.14 m/s slower, 54% less pitch instability, not yet self-righting", { x: 0.6, y: 5.85, w: 12.1, h: 0.4, fontSize: 18, align: "center", color: "FFFFFF" });
  tag(s);
  s.addNotes("18 seconds. All four use exactly 250 cm². The central vent lands at 6.31 m/s, 0.14 slower than the plain canopy, with 54% less pitch instability. It is not yet self-righting. The two outer shapes are free-form designs, and the large hole is the worst here, at 7.20. These are CFD estimates, not measurements. @@ IF ASKED, WHAT 12% MEANS: the hole equals 12% of the plastic area, or 10.7% of the outline. Plastic stays at 250 cm², so the outline grows slightly. @@ IF ASKED, NUMBERS: drag area 243.6 cm² against 219.5 for the plain canopy. Cm_alpha +2.25 against +4.89, in 1e-3 per degree. @@ IF ASKED, WHY A HOLE HELPS: in CFD it reaches a larger drag area and is less unstable. Controlled venting is the likely reason, but we have not tested it directly. @@ IF ASKED, SELF-RIGHTING: only 4 of 45 designs are. The slowest of those lands at 6.91 m/s, so nothing is both slow and self-righting yet.");

  // Open area
  s = page();
  s.addText("Small holes gave the lowest estimates", { placeholder: "title" });
  const DATA = JSON.parse(fs.readFileSync(M("deck_data.json")));
  const isV = (p) => p[2] === "vent12";
  s.addChart(pres.charts.SCATTER, [{ name: "Open area", values: DATA.pts.map((p) => p[0]) },
    { name: "45 converged designs", values: DATA.pts.map((p) => isV(p) ? null : p[1]) }, { name: "12% vent", values: DATA.pts.map((p) => isV(p) ? p[1] : null) }],
    { x: 0.6, y: 1.4, w: 8.2, h: 5.3, chartColors: [LILAC, ORANGE], lineSize: 0, lineDataSymbol: "circle", lineDataSymbolSize: 11, showLegend: true, legendPos: "b", legendFontSize: 14, legendFontFace: "+mn-lt", legendColor: LIGHT,
      showCatAxisTitle: true, catAxisTitle: "Open area, % of outline", catAxisTitleFontSize: 14, catAxisTitleColor: LIGHT, catAxisTitleFontFace: "+mn-lt",
      showValAxisTitle: true, valAxisTitle: "Landing speed, m/s (lower is better)", valAxisTitleFontSize: 14, valAxisTitleColor: LIGHT, valAxisTitleFontFace: "+mn-lt",
      valAxisMinVal: 6.2, valAxisMaxVal: 7.3, valAxisMajorUnit: 0.2, valAxisLabelFormatCode: "0.0", catAxisMinVal: 0, catAxisMaxVal: 60, catAxisMajorUnit: 10, valGridLine: { color: GRID, size: 0.75 }, ...chartText });
  stat(s, "~10%", "open gave the best results", 9.2, 1.6, 3.5);
  stat(s, "> 30%", "drag falls away, and speed rises", 9.2, 3.2, 3.5, LILAC);
  txt(s, "Each dot is one design, all with 250 cm² of plastic.", { x: 9.2, y: 4.8, w: 3.5, h: 0.8, fontSize: 16 });
  tag(s);
  s.addNotes("12 seconds. Each dot is one CFD design. The lowest estimates sit around 10% open. Past about 30%, drag falls away and landing speed climbs. Drag tracks how much area the canopy inflates to. @@ IF ASKED, NO-HOLE DESIGNS: the 19 designs at 0% open had a median of 6.50 m/s, so a hole is not needed to land under 6.5, but the best results all had one. @@ IF ASKED, IS 10% EXACT: no. Only 13 designs fall between 1% and 15%, so it is a region, not a proven optimum. Their median is 6.43, so a small hole alone does not guarantee a good result.");

  // Flow
  s = page();
  s.addText("What the air is doing", { placeholder: "title" });
  s.addImage({ path: M("flow_hole.png"), x: 0.6, y: 1.35, w: 5.68, h: 4.97, altText: "Air running through a large hole in a canopy" });
  s.addImage({ path: M("flow_tilt.png"), x: 6.9, y: 1.35, w: 3.61, h: 4.97, altText: "Lopsided vortices behind a canopy tilted 10 degrees" });
  txt(s, "Big hole: air runs straight through", { x: 0.6, y: 6.4, w: 5.68, h: 0.35, fontSize: 16 });
  txt(s, "Tilted 10°: lopsided wake (coarse mesh)", { x: 6.9, y: 6.4, w: 5.0, h: 0.35, fontSize: 16 });
  s.addNotes("10 seconds. Left: time-accurate CFD on a canopy with a large opening. Right: an earlier coarse-mesh run tilted 10 degrees, which shows why stability is hard. @@ LEFT IMAGE: free03, about 26% open. It is self-righting but lands at 6.91 m/s. @@ RIGHT IMAGE: an older slit canopy on a coarse mesh, so use it to show the idea only. @@ IF ASKED, WHY NOT THE VENT: we lost the vent's flow fields when the rented machines shut down. Its force results were saved.");

  // Search
  s = page();
  s.addText("Nine design variables, 200 evaluations", { placeholder: "title" });
  video(s, "ga_evolve.mp4", "ga_cover.png", 0.6, 1.5, 8.4, 4.725);
  [["1", "GA evolves a population"], ["2", "Surrogate model scores fitness"], ["3", "Best designs get fresh CFD"]].forEach(([n, t], i) => {
    const y = 1.6 + i * 1.5;
    txt(s, n, { x: 9.3, y, w: 0.6, h: 1.1, fontSize: 40, bold: true, color: ORANGE, fontFace: "Cambria", valign: "middle" });
    txt(s, t, { x: 9.95, y, w: 2.8, h: 1.1, fontSize: 20, color: "FFFFFF", valign: "middle" });
  });
  txt(s, "Grey shapes: infeasible, could not be cut or predicted not to inflate", { x: 0.6, y: 6.3, w: 8.4, h: 0.3, fontSize: 14, color: MUTED });
  s.addNotes("30 seconds. The GA evolves a population of designs, the surrogate model scores their fitness, and the best designs later get fresh CFD. Click the video. A design that cannot be cut, or is predicted not to inflate, gets a marked penalty. Grey shapes were rejected. Budget: 200 evaluations, on surrogate scores with test noise. @@ WHY A GA: it handles 9 variables and does not need gradients. @@ HOW: each generation scores 20 designs, keeps good ones, then uses crossover and mutation. This video is a real run, 10 generations and 200 designs. @@ FITNESS: lowest predicted landing speed, with 0.03 m/s test noise. Infeasible designs get a marked penalty. @@ IF ASKED, THE SPEED ON SCREEN: it is a noisy surrogate score, not a real speed.");
  s = page();
  s.addText("It reinvented the central hole", { placeholder: "title" });
  s.addImage({ path: M("ga_final.png"), x: 1.3, y: 1.3, w: 9.6, h: 5.4, altText: "Final GA generation, nearly all with central holes" });
  s.addNotes("6 seconds. No rule told it to do this. @@ BE CAREFUL: no rule told it to make a hole, but the surrogate was trained on CFD data that included holed designs, and open area is one of its features. So it found the hole from the data, not from nothing.");

  // Surrogate check
  s = page();
  s.addText("Fresh CFD exposed the surrogate's optimism", { placeholder: "title" });
  const wins = DATA.win.filter((w) => w[1] === "ga");
  s.addChart(pres.charts.BAR, [{ name: "CFD minus surrogate", labels: ["GA winner 1", "GA winner 2", "GA winner 3"], values: wins.map((w) => Number((w[3] - w[2]).toFixed(3))) }],
    { x: 0.6, y: 1.5, w: 6.3, h: 4.8, barDir: "col", chartColors: [ORANGE], barGapWidthPct: 60, showTitle: true, title: "Surrogate error: CFD minus prediction, m/s", titleFontSize: 15, titleColor: LIGHT, titleFontFace: "+mn-lt", showLegend: false,
      showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 16, dataLabelColor: LIGHT, dataLabelFormatCode: "+0.00", dataLabelFontFace: "+mn-lt", valAxisHidden: true, valAxisMinVal: 0, valAxisMaxVal: 0.2, valGridLine: { style: "none" }, ...chartText });
  s.addTable([[hdr0("Design", "left"), hdr0("Predicted (m/s)", "right"), hdr0("CFD (m/s)", "right")],
    ...wins.map((w, i) => [cell0("GA winner " + (i + 1)), cell0(w[2].toFixed(2), { align: "right" }), cell0(w[3].toFixed(2), { align: "right" })])],
    { x: 7.3, y: 1.7, w: 5.4, colW: [2.2, 1.7, 1.5], rowH: 0.42, objectName: "Surrogate check table" });
  txt(s, "Optimising on a model also finds the model's mistakes.", { x: 7.3, y: 4.0, w: 5.4, h: 0.9, fontSize: 22, bold: true, color: "FFFFFF" });
  txt(s, "All five checked winners inflated stably.", { x: 7.3, y: 5.05, w: 5.4, h: 0.4, fontSize: 18 });
  tag(s);
  s.addNotes("15 seconds. This is the check. The GA's top designs were predicted around 6.27 m/s. Fresh CFD put them 0.06 to 0.17 slower. When you optimise on a model, you also find the model's mistakes. All five checked winners inflated stably. @@ THE FIVE WINNERS IN CFD: 6.33, 6.36, 6.41, 6.41 and 6.44 m/s. Three came from GA, and these are shown on the slide. @@ IF ASKED, THE OTHER TWO: they came from other methods and were predicted almost exactly, within 0.01 m/s, but their predictions were also around 6.40. So the error grew with how hard the search pushed. That is only 5 designs, so treat it as a clue. @@ WHY THE SURROGATE WAS OPTIMISTIC: it trained on only about 40 free-form designs, and search goes straight to the places where its errors look good. A better search cannot fix that.");

  // Vent against search winner
  s = page();
  s.addText("The vent keeps the lowest checked estimate", { placeholder: "title" });
  [["quiz_win0.png", "Search winner", "6.33", false], ["quiz_vent12.png", "12% vent", "6.31", true]].forEach(([img, l, v, win], i) => {
    const x = 1.2 + i * 5.8;
    s.addImage({ path: M(img), x: x + 0.65, y: 1.45, w: 2.9, h: 2.9, altText: l });
    txt(s, l, { x, y: 4.4, w: 4.2, h: 0.5, fontSize: 28, bold: true, align: "center", color: win ? ORANGE : "FFFFFF", fontFace: "Cambria" });
    if (!win) txt(s, "Surrogate predicted 6.27 m/s", { x, y: 4.92, w: 4.2, h: 0.4, fontSize: 18, align: "center" });
    txt(s, (win ? "CFD: " : "CFD check: ") + v + " m/s", { x, y: 5.32, w: 4.2, h: 0.6, fontSize: 24, bold: true, align: "center", color: win ? ORANGE : MUTED });
  });
  txt(s, "A 0.02 m/s gap, with no uncertainty estimate yet", { x: 0.6, y: 6.1, w: 12.1, h: 0.4, fontSize: 18, align: "center", color: "FFFFFF" });
  tag(s);
  s.addNotes("15 seconds. The best search winner checked at 6.33, against 6.31 for the hand-made vent. The gap is only 0.02, and we have no uncertainty estimate yet. So the vent simply has the lowest checked estimate. The search still got close, starting from random shapes. @@ DO NOT SAY the vent is decisively better. @@ IF ASKED, STABILITY: Cm_alpha is +2.53 for the search winner and +2.25 for the vent, in 1e-3 per degree. Neither is self-righting.");

  // Benchmark
  s = page();
  s.addText("GA and PSO led; tabu search trailed", { placeholder: "title" });
  const lab = ["GA", "PSO", "Multi-objective GA", "Bayesian opt.", "Sim. annealing", "Tabu search"];
  s.addChart(pres.charts.BAR, [{ name: "vs random search", labels: lab, values: [-0.052, -0.041, -0.025, -0.019, -0.009, 0.163] }],
    { x: 0.6, y: 1.5, w: 6.3, h: 4.75, barDir: "bar", chartColors: [ORANGE], barGapWidthPct: 45, catAxisOrientation: "maxMin", catAxisLabelPos: "low",
      showTitle: true, title: "Median best score vs random search, m/s (lower is better)", titleFontSize: 15, titleColor: LIGHT, titleFontFace: "+mn-lt", showLegend: false,
      showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 14, dataLabelColor: LIGHT, dataLabelFormatCode: "+0.000;-0.000", dataLabelFontFace: "+mn-lt",
      valAxisHidden: true, valAxisMinVal: -0.1, valAxisMaxVal: 0.22, valGridLine: { style: "none" }, ...chartText });
  s.addTable([[hdr("Method", "left"), hdr("Median (m/s)", "right"), hdr("IQR (m/s)", "right")],
    ...[["GA", "6.260", "0.020"], ["PSO", "6.271", "0.018"], ["Multi-objective GA", "6.288", "0.041"], ["Bayesian optimization", "6.293", "0.023"], ["Simulated annealing", "6.303", "0.043"], ["Random search", "6.312", "0.016"], ["Tabu search", "6.475", "0.248"]]
      .map(([m, a, b]) => [cell(m), cell(a, { align: "right" }), cell(b, { align: "right" })])],
    { x: 7.3, y: 1.5, w: 5.4, colW: [2.5, 1.5, 1.4], rowH: 0.36, objectName: "Benchmark table" });
  txt(s, "200 evaluations × 10 runs. Objective: best surrogate speed found, with 0.03 m/s test noise. IQR: spread across runs.", { x: 7.3, y: 5.2, w: 5.4, h: 1.0, fontSize: 15, color: MUTED });
  tag(s);
  s.addNotes("20 seconds. Each method got 200 evaluations over 10 runs. The objective is the best surrogate speed found, with test noise, so this ranks methods and does not give real speeds. Numbers are medians, and IQR shows the spread across runs. GA and PSO led, and tabu trailed with by far the widest spread. @@ WHY SO MANY METHODS: comparing them is the project. Our title is a comparative evaluation, and our second question is which methods work best. Each also has a job: LHS samples, PCA, AE and VAE compress, GP predicts, and the rest search. @@ WHY THEY DID NOT BEAT THE VENT: all of them searched the surrogate, not real physics. So the main limit was the surrogate, not one algorithm. @@ REASONS BELOW ARE LIKELY, NOT TESTED. @@ TABU SEARCH, 6.475: the clear worst, and very inconsistent. It moves in fixed steps, a poor fit for 9 continuous variables. @@ RANDOM SEARCH, 6.312: close to the others because many designs score well on the surrogate, so even random picks do fine in 200 tries. @@ SIMULATED ANNEALING, 6.303: only just beat random. It tries one design at a time, so 200 evaluations may be too few in 9 dimensions. @@ BAYESIAN OPTIMIZATION, 6.293: middle of the pack despite being built for few evaluations. Noise and infeasible designs may hurt its model, and we have not tuned it. @@ MULTI-OBJECTIVE GA, 6.288: not a real loser, because it also optimises stability. @@ GA 6.260 AND PSO 6.271: both use many designs at once, which may help them cope with noise. @@ IF ASKED, LIMIT: this ranks methods on one surrogate with one budget and our settings. It does not prove GA is best in general. @@ IF ASKED, GRADIENT: outside this talk's scope, so keep it brief.");

  // Plan
  s = page();
  s.addText("Next: a better surrogate, then real drops decide", { placeholder: "title" });
  [["1", "Bayesian optimization", "Feed the CFD checks back into the surrogate"], ["2", "Multi-objective GA (NSGA-II)", "Find the Pareto front of speed against stability"], ["3", "Real drops, more repeats", "Weigh the payload and test the hole designs"]].forEach(([n, t, d], i) => {
    const y = 1.55 + i * 1.3;
    txt(s, n, { x: 0.6, y, w: 0.8, h: 1.1, fontSize: 48, bold: true, color: ORANGE, fontFace: "Cambria", valign: "middle" });
    txt(s, t, { x: 1.5, y, w: 6.2, h: 0.55, fontSize: 26, bold: true, color: "FFFFFF" });
    txt(s, d, { x: 1.5, y: y + 0.56, w: 6.2, h: 0.5, fontSize: 18 });
  });
  stat(s, "0.14 m/s", "vent gain over the plain canopy", 8.3, 1.65, 4.4);
  stat(s, "0.139 m/s", "smallest gap 3 repeats can detect, assuming 0.06 m/s drop noise", 8.3, 3.2, 4.4, LILAC);
  txt(s, "So 3 repeats per design is not enough.", { x: 8.3, y: 4.95, w: 4.4, h: 0.45, fontSize: 18, color: "FFFFFF" });
  tag(s);
  s.addNotes("20 seconds. Our objective stays the same: minimise landing speed, with pitch stability alongside it. Next we feed the CFD checks back through Bayesian optimization, then use a multi-objective GA, NSGA-II, to find the Pareto front of speed against stability. Then real drops decide. The vent's 0.14 m/s gain sits right at what 3 repeats can detect, so we need more repeats. UPDATE if drops are done: add measured speeds. @@ WHY THESE STEPS: more CFD data should reduce surrogate error, and Bayesian optimization chooses which designs to run next. A multi-objective GA fits because speed and stability pull against each other. @@ 0.139 M/S: the gap needed to reach 4 standard errors, with 0.06 m/s noise per drop and 3 repeats. The noise is an assumption until we drop. @@ REAL DROPS STILL NEED: weighing the payload, IMU wiring, the exact RealSense model and recorder, and the hole stencils added to the drop schedule.");

  // Backup slides, for questions only
  s = page();
  s.addText("Backup: what each course method does", { placeholder: "title" });
  const row = (a, b) => [cell(a, { bold: true, color: "FFFFFF" }), cell(b)];
  s.addTable([["Latin hypercube sampling", "DOE: spreads sample designs evenly across the design space"], ["PCA, autoencoder, VAE", "Dimensionality reduction: compress canopy shapes and test how many dimensions they need"],
    ["Gaussian process", "Surrogate model for drag and stability, from shape features"], ["GA, multi-objective GA", "Evolve a population: one objective, or a Pareto front (NSGA-II)"],
    ["Particle swarm optimization", "A swarm of designs moves toward the best found"], ["Simulated annealing", "Random steps, accepting worse moves less often over time"],
    ["Tabu search", "Local search that bans recently visited designs"], ["Bayesian optimization", "A surrogate model and acquisition function pick the next evaluation"]].map(([a, b]) => row(a, b)),
    { x: 0.6, y: 1.5, w: 12.1, colW: [3.4, 8.7], rowH: 0.55, objectName: "Method table" });
  s.addNotes("Backup. Use only for questions. @@ IF ASKED, GA AGAINST PSO: a GA breeds and replaces designs. PSO keeps the same designs and moves them. @@ IF ASKED, BAYESIAN OPTIMIZATION: the Gaussian process gives a prediction and an uncertainty, and the acquisition function uses both, such as expected improvement. @@ IF ASKED, PARETO FRONT: designs where you cannot improve one objective without hurting the other.");

  s = page();
  s.addText("Backup: measurement pipeline", { placeholder: "title" });
  chain(s, ["RealSense colour + depth", "BNO085 IMU", "LED clock sync", "Kalman filter", "Landing speed"], 0.6, 1.6, 2.38, 1.0, 0.05, 15, [4]);
  stat(s, "≈ 0.04 m/s", "fused speed error against simulator truth, one test drop", 0.6, 3.2, 3.8);
  stat(s, "≈ 0.39 m/s", "camera-only error: it sees about the last 0.2 s of the fall", 4.75, 3.2, 3.8, LILAC);
  stat(s, "≈ 2 ms", "clock sync error", 8.9, 3.2, 3.8);
  txt(s, "Software check on an earlier payload (V1). No markers fit on the payload, so the camera tracks colour and depth. Failed readings get a marked penalty and are never replaced with a made-up value.", { x: 0.6, y: 4.9, w: 12.1, h: 1.0, fontSize: 18 });
  s.addNotes("Backup. Use only for questions. These are simulated, software-level checks from the first version of the pipeline. @@ IF ASKED: the Kalman filter combines camera and IMU. These sensor methods are how we capture data, so describe them in one line and do not teach them.");

  s = page();
  s.addText("Backup: validation and assumptions", { placeholder: "title" });
  s.addTable([["CFD", "OpenFOAM, k-omega SST, 7 m/s, 0° and 10°. Disc +5.6%, cup +6.8% against reference drag"],
    ["Stability", "Cm_alpha is a slope from two angles only"], ["Inflation", "Quasi-static shape under uniform pressure. No feedback from CFD pressure to shape"],
    ["Data kept", "45 converged designs of 51. Inflation scan: 64% of 780 shapes stable"], ["Surrogate", "Optimistic by 0.06 to 0.17 m/s on the three GA winners"],
    ["Payload", "95 g payload and 3 g canopy assumed, not weighed"], ["Real drops", "Not yet in these results. All speeds are simulation estimates"]].map(([a, b]) => row(a, b)),
    { x: 0.6, y: 1.5, w: 12.1, colW: [2.2, 9.9], rowH: 0.6, objectName: "Assumptions table" });
  s.addNotes("Backup. Use only for questions. @@ IF ASKED, WHAT ISN'T DONE: real drops, calibration, a formal uncertainty estimate, and any mesh convergence claim. Do not claim a mesh study.");

  const out = path.join(DIR, "parachute_midway_2026-11-03.pptx");
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  const JSZip = require("jszip");
  const zip = await JSZip.loadAsync(fs.readFileSync(out));
  // notes: one paragraph per point (@@ marks a break)
  for (const f of Object.keys(zip.files).filter((n) => /^ppt\/notesSlides\/notesSlide\d+\.xml$/.test(n))) {
    const x = await zip.file(f).async("string");
    zip.file(f, x.replace(/<a:p>(?:(?!<\/a:p>).)*?@@(?:(?!<\/a:p>).)*?<\/a:p>/gs, (p) => {
      const [head, tail] = [p.slice(0, p.indexOf("<a:t>") + 5), p.slice(p.indexOf("</a:t>"))];
      const parts = p.slice(head.length, p.length - tail.length).split(" @@ ");
      return parts.map((t) => head + t + tail).join("");
    }));
  }
  fs.writeFileSync(out, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
  console.log(out);
})();
