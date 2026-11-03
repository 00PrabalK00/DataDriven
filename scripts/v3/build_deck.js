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

  // Title
  let s = pres.addSlide({ masterName: "TITLE" });
  s.addText("Can a data-driven search beat a hole in the middle?", { placeholder: "title" });
  s.addText("Comparative evaluation of data-driven design methods for parachute shape and slit optimization", { placeholder: "body" });
  s.addImage({ path: M("inflate_final.png"), x: 6.6, y: 0.35, w: 6.73, h: 6.73, altText: "Inflated canopy with a central vent and suspension lines" });
  txt(s, "ROB-GY 7863B, NYU Tandon", { x: 0.7, y: 6.45, w: 5.8, h: 0.3, fontSize: 14, color: MUTED });
  s.addNotes("8 seconds. Introduce the team and ask the question.");

  // Problem
  s = page();
  s.addText("250 cm² of plastic. How slowly can it land?", { placeholder: "title" });
  s.addMedia({ type: "video", path: M("camera_drop_slowmo.mp4"), cover: b64("slowmo_cover.png"), x: 0.6, y: 1.7, w: 8.3, h: 3.4 });
  stat(s, "8.9 m/s", "free fall", 9.3, 1.7, 3.4);
  stat(s, "6.3 m/s", "our best so far (CFD)", 9.3, 3.3, 3.4, LILAC);
  txt(s, "Goal: slowest landing, stable flight", { x: 0.6, y: 5.5, w: 12.1, h: 0.5, fontSize: 24, bold: true, color: "FFFFFF" });
  s.addNotes("25 seconds. Click the video. Same plastic every time, any 2D shape. We minimise speed before impact and track pitch stability, Cm alpha, as the second objective. Free fall from 4 m is 8.9 m/s. Payload mass is assumed until weighed.");

  // Slits fail -> encodings
  s = page();
  s.addText("Our first idea failed: slits barely open", { placeholder: "title" });
  s.addImage({ path: M("slit_3d.png"), x: 0.6, y: 1.5, w: 3.9, h: 3.28, altText: "Inflated canopy with radial slits" });
  txt(s, "< 1 mm", { x: 0.6, y: 5.0, w: 3.9, h: 0.75, fontSize: 44, bold: true, color: ORANGE });
  [["enc_param.png", "3 numbers", "Slits"], ["enc_cut.png", "7 numbers", "Holes"], ["enc_free.png", "9 numbers", "Free-form"]].forEach(([img, k, d], i) => {
    const x = 5.0 + i * 2.62;
    s.addImage({ path: M(img), x: x + 0.1, y: 1.7, w: 2.2, h: 2.2, altText: k + " encoding example" });
    txt(s, k, { x, y: 4.2, w: 2.4, h: 0.45, fontSize: 24, bold: true, color: i === 2 ? ORANGE : "FFFFFF", fontFace: "Cambria" });
    txt(s, d, { x, y: 4.7, w: 2.4, h: 0.4, fontSize: 18 });
  });
  s.addNotes("30 seconds. We started with slits. CFD on 36 designs showed under 1 mm of opening, so slits were not doing anything. We changed the encoding: 3 parameters, then cut-outs with 7, then a free-form field of 61 Gaussian bumps controlled by 9 weights. Every design must be cuttable: one piece, no tiny holes, no thin bridges. 78% of samples pass.");

  // Dimensionality reduction
  s = page();
  s.addText("Nine dimensions rebuild almost any canopy", { placeholder: "title" });
  const ks = ["2", "4", "6", "9", "16"];
  s.addChart(pres.charts.LINE, [
    { name: "PCA", labels: ks, values: [0.827, 0.893, 0.914, 0.936, 0.958] },
    { name: "Autoencoder", labels: ks, values: [0.893, 0.939, 0.966, 0.971, 0.972] },
    { name: "VAE", labels: ks, values: [0.897, 0.939, 0.961, 0.966, 0.959] }],
    { x: 0.6, y: 1.4, w: 6.3, h: 5.1, chartColors: [MUTED, ORANGE, LILAC], lineSize: 3, lineDataSymbolSize: 8,
      showTitle: false, showLegend: true, legendPos: "b", legendFontSize: 14, legendFontFace: "+mn-lt", legendColor: LIGHT,
      showCatAxisTitle: true, catAxisTitle: "Dimensions", catAxisTitleFontSize: 14, catAxisTitleColor: LIGHT, catAxisTitleFontFace: "+mn-lt",
      showValAxisTitle: true, valAxisTitle: "Shape overlap (IoU)", valAxisTitleFontSize: 14, valAxisTitleColor: LIGHT, valAxisTitleFontFace: "+mn-lt",
      valAxisMinVal: 0.8, valAxisMaxVal: 1.0, valAxisMajorUnit: 0.05, valAxisLabelFormatCode: "0.00", valGridLine: { color: GRID, size: 0.75 }, ...chartText });
  s.addImage({ path: M("vae_samples.png"), x: 7.3, y: 1.6, w: 5.4, h: 2.03, altText: "Canopy shapes generated by the VAE" });
  txt(s, "Shapes the VAE invented", { x: 7.3, y: 3.72, w: 5.4, h: 0.35, fontSize: 18, color: "FFFFFF" });
  stat(s, "0.97", "autoencoder at 9-D, on 1,883 canopies", 7.3, 4.5, 5.4);
  s.addNotes("25 seconds. PCA, autoencoder and VAE on 1,883 canopy masks. Nonlinear methods reach about 0.97 at 9 dimensions, against 0.94 for PCA. That matches our 9-weight encoding, so we search those weights directly. At 9-D, 66% of VAE shapes are one piece, so the VAE stays a generator to test later.");

  // Data capture and validation
  s = page();
  s.addText("Every shape gets CFD. Every drop gets sensors.", { placeholder: "title" });
  s.addMedia({ type: "video", path: M("inflate.mp4"), cover: b64("inflate_cover.png"), x: 0.6, y: 1.5, w: 5.0, h: 5.0 });
  const flow = (y, steps) => steps.forEach((t, i) => s.addText(t, { shape: pres.shapes.PENTAGON, x: 6.0 + i * 2.25, y, w: 2.2, h: 0.85, fill: { color: i === 2 ? ORANGE : PANEL },
    color: i === 2 ? BG : LIGHT, bold: i === 2, fontSize: 16, align: "center", valign: "middle", margin: 3 }));
  flow(1.6, ["Inflate", "OpenFOAM", "Drag, stability"]);
  flow(2.7, ["Camera + IMU", "Pose filter", "Landing speed"]);
  stat(s, "1.235", "disc Cd, reference 1.17", 6.0, 4.3, 3.2);
  stat(s, "1.516", "cup Cd, reference 1.42", 9.4, 4.3, 3.2, LILAC);
  s.addNotes("30 seconds. Click the video. Each shape is inflated numerically, then run through OpenFOAM at 0 and 10 degrees. Drops, simulated or real, go through the same RealSense and BNO085 code. Validation: disc and cup are within 7% of Hoerner's reference drag values. Real drops are the check still to come.");

  // Vote 1
  const four = [["quiz_free07.png", "A", "6.40"], ["quiz_base_q2.8.png", "B", "6.45"], ["quiz_vent12.png", "C", "6.31"], ["quiz_free52.png", "D", "7.20"]];
  const vote1 = (reveal) => {
    s = page();
    s.addText(reveal ? "A small hole wins. A big hole just leaks." : "Same plastic. Which one lands slowest?", { placeholder: "title" });
    four.forEach(([img, l, v], i) => {
      const x = 0.6 + i * 3.08, win = reveal && l === "C";
      s.addImage({ path: M(img), x: x + 0.1, y: 1.65, w: 2.7, h: 2.7, altText: "Canopy " + l, transparency: reveal && !win ? 60 : 0 });
      txt(s, l, { x, y: 4.5, w: 2.9, h: 0.65, fontSize: 36, bold: true, align: "center", color: win ? ORANGE : "FFFFFF", fontFace: "Cambria" });
      if (reveal) txt(s, v + " m/s", { x, y: 5.2, w: 2.9, h: 0.65, fontSize: 32, bold: true, align: "center", color: win ? ORANGE : MUTED });
    });
    return s;
  };
  vote1(false).addNotes("12 seconds. Ask the room to vote by hand: A, B, C or D. All four use exactly 250 cm². Then click.");
  vote1(true).addNotes("20 seconds. C is the 12% vent: 6.31 m/s, 0.14 m/s slower than the plain canopy B, and pitch instability drops 54%, though it is not yet self-righting. Across 45 converged CFD designs, about 10% open is the sweet spot. Past about 30%, drag falls away. CFD estimates, not measurements.");

  // Flow
  s = page();
  s.addText("What the air is doing", { placeholder: "title" });
  s.addImage({ path: M("flow_hole.png"), x: 0.6, y: 1.35, w: 5.68, h: 4.97, altText: "Air running through a large hole in a canopy" });
  s.addImage({ path: M("flow_tilt.png"), x: 6.9, y: 1.35, w: 3.61, h: 4.97, altText: "Lopsided vortices behind a canopy tilted 10 degrees" });
  txt(s, "Big hole: air runs straight through", { x: 0.6, y: 6.4, w: 5.68, h: 0.35, fontSize: 16 });
  txt(s, "Tilted 10°: lopsided wake (coarse mesh)", { x: 6.9, y: 6.4, w: 5.0, h: 0.35, fontSize: 16 });
  s.addNotes("20 seconds. Left: time-accurate CFD on a canopy with a large opening. Right: an earlier coarse-mesh run on a slit canopy tilted 10 degrees, showing why stability is hard.");

  // Search
  s = page();
  s.addText("Nine free numbers. What will a GA find?", { placeholder: "title" });
  s.addMedia({ type: "video", path: M("ga_evolve.mp4"), cover: b64("ga_cover.png"), x: 1.3, y: 1.3, w: 9.6, h: 5.4 });
  s.addNotes("40 seconds. Before clicking, ask what shape the room expects. Click the video. Objective: lowest landing speed, with a marked penalty if a design cannot be cut or is predicted not to inflate. Grey shapes were rejected. This is a real GA run on the CFD surrogate; scores include test noise. Budget: 200 evaluations.");
  s = page();
  s.addText("It reinvented the central hole", { placeholder: "title" });
  s.addImage({ path: M("ga_final.png"), x: 1.3, y: 1.3, w: 9.6, h: 5.4, altText: "Final GA generation, nearly all with central holes" });
  s.addNotes("10 seconds. No rule told it to do this.");

  // Vote 2
  const vote2 = (reveal) => {
    s = page();
    s.addText(reveal ? "The simple vent still wins, for now" : "Search winner or our hand-made vent?", { placeholder: "title" });
    [["quiz_win0.png", "Search winner", "6.33", false], ["quiz_vent12.png", "12% vent", "6.31", true]].forEach(([img, l, v, win], i) => {
      const x = 1.2 + i * 5.8, c = reveal && win;
      s.addImage({ path: M(img), x: x + 0.65, y: 1.5, w: 3.2, h: 3.2, altText: l });
      txt(s, l, { x, y: 4.8, w: 4.5, h: 0.55, fontSize: 28, bold: true, align: "center", color: c ? ORANGE : "FFFFFF", fontFace: "Cambria" });
      if (reveal) txt(s, v + " m/s", { x, y: 5.4, w: 4.5, h: 0.7, fontSize: 36, bold: true, align: "center", color: c ? ORANGE : MUTED });
    });
    return s;
  };
  vote2(false).addNotes("10 seconds. Second vote. The surrogate predicted 6.27 for the search winner. Then click.");
  vote2(true).addNotes("20 seconds. In real CFD, all five winners inflated stably, but the surrogate was optimistic by 0.06 to 0.17 m/s and none beat the vent. Optimising on a model finds the model's mistakes too. These are CFD estimates.");

  // Methods + plan
  s = page();
  s.addText("Next: better surrogate, then real drops decide", { placeholder: "title" });
  const lab = ["GA", "PSO", "NSGA-II", "BO", "SA", "Tabu"];
  s.addChart(pres.charts.BAR, [{ name: "vs random search", labels: lab, values: [-0.052, -0.041, -0.025, -0.019, -0.009, 0.163] }],
    { x: 0.6, y: 1.4, w: 6.6, h: 4.9, barDir: "bar", chartColors: [ORANGE], barGapWidthPct: 45, catAxisOrientation: "maxMin", catAxisLabelPos: "low",
      showTitle: true, title: "Best score vs random search, m/s (lower is better)", titleFontSize: 15, titleColor: LIGHT, titleFontFace: "+mn-lt", showLegend: false,
      showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 14, dataLabelColor: LIGHT, dataLabelFormatCode: "+0.000;-0.000", dataLabelFontFace: "+mn-lt",
      valAxisHidden: true, valAxisMinVal: -0.1, valAxisMaxVal: 0.22, valGridLine: { style: "none" }, ...chartText });
  [["1", "Feed CFD back into BO"], ["2", "NSGA-II: speed vs stability"], ["3", "Real drops, more repeats"]].forEach(([n, t], i) => {
    const y = 1.7 + i * 1.5;
    txt(s, n, { x: 7.7, y, w: 0.7, h: 0.9, fontSize: 44, bold: true, color: ORANGE, fontFace: "Cambria", valign: "middle" });
    txt(s, t, { x: 8.5, y, w: 4.2, h: 0.9, fontSize: 22, color: "FFFFFF", valign: "middle" });
  });
  s.addNotes("30 seconds. Surrogate benchmark, 200 evaluations, 10 runs each, medians: it ranks methods, not real speeds. GA and PSO lead, tabu trails. Plans: update the surrogate with the CFD points through BO, use NSGA-II for the speed and stability trade-off, and test in real drops. The vent's 0.14 m/s gain sits right at what 3 repeats can detect, so we need more repeats. UPDATE if the Oct 31 drops are done: add measured speeds.");

  const out = path.join(DIR, "parachute_midway_2026-11-03.pptx");
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  // fade on the slides that reveal a vote or the GA result, so the answer appears in place
  const JSZip = require("jszip");
  const zip = await JSZip.loadAsync(fs.readFileSync(out));
  for (const n of [7, 10, 12]) {
    const f = `ppt/slides/slide${n}.xml`;
    const x = await zip.file(f).async("string");
    zip.file(f, x.replace("</p:clrMapOvr>", '</p:clrMapOvr><p:transition spd="med"><p:fade/></p:transition>'));
  }
  fs.writeFileSync(out, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
  console.log(out);
})();
