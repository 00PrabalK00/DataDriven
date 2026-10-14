function rep = feasibilitySweep(opts)
%FEASIBILITYSWEEP Go/no-go check: over a grid of AERODYNAMIC ASSUMPTIONS (not one assumed truth),
%how large is the design-to-design landing-speed spread compared with expected measurement noise?
% Reports a range, never a winner (evidence level L2).
arguments
    opts.designs double = []          % N x 3; default: DOE designs
    opts.cdScale double = [0.6 0.8 1.0]
    opts.slitStrength double = [0 1 3] % 0 = slits have no effect, 1 = prior map, 3 = strong
    opts.tauScale double = [0.5 1 2]
    opts.mass double = [0.080 0.090 0.105]
    opts.height double = [4 5 6]
    opts.noiseSd double = 0.06         % per-drop pre-impact speed estimation noise (m/s), from pipeline validation
    opts.repeats double = 3
    opts.outDir (1,:) char = fullfile(chute.util.repoRoot(), 'results', 'feasibility')
end
cfg = chute.bridge.config();
D = opts.designs;
if isempty(D), D = chute.doe.lhsDesigns(16, 1); end
nD = size(D, 1);
% prior-map parameters and the no-slit counterpart of each design
Kp = zeros(nD,1); K0 = zeros(nD,1); tau = zeros(nD,1);
for i = 1:nD
    g = chute.geom.geometry(D(i,1), D(i,2), D(i,3));
    g0 = chute.geom.geometry(D(i,1), 0, D(i,3));
    Kp(i) = g.aero.K_open_m2; K0(i) = g0.aero.K_open_m2; tau(i) = g.aero.tau_s;
end
Kbox = chute.util.payloadKbox(cfg);
[A, B, C, M, H] = ndgrid(opts.cdScale, opts.slitStrength, opts.tauScale, opts.mass, opts.height);
nA = numel(A);
spread = zeros(nA,1); sdD = zeros(nA,1); vmean = zeros(nA,1); vfree = zeros(nA,1);
for a = 1:nA
    v = zeros(nD,1);
    for i = 1:nD
        Ko = A(a) * (K0(i) + B(a) * (Kp(i) - K0(i)));
        p = struct('m', M(a) + cfg.canopy.mass_kg, 'g', cfg.physics.g, 'rho', cfg.physics.rho, ...
            'K_i', 0.3*Ko, 'K_o', Ko, 'tau', C(a)*tau(i), 'K_box', Kbox, 'h0', H(a), 'v0', 0);
        s = chute.ode.simulateDrop(p);
        v(i) = s.v_contact;
    end
    spread(a) = max(v) - min(v); sdD(a) = std(v); vmean(a) = mean(v);
    vfree(a) = sqrt(2 * cfg.physics.g * H(a));
end
se = opts.noiseSd / sqrt(opts.repeats);
resolvable = spread > 4 * se;   % best vs worst separable with 'repeats' drops each (~2 sigma each side)
T = table(A(:), B(:), C(:), M(:), H(:), vmean, vfree, spread, sdD, spread ./ se, resolvable, ...
    'VariableNames', {'cdScale','slitStrength','tauScale','mass_kg','height_m','meanLandingSpeed', ...
    'freeFallSpeed','designSpread','designSD','spreadOverSE','resolvable'});
rep.table = T;
rep.fractionResolvable = mean(resolvable);
sel = abs(M(:) - cfg.payload.mass_kg) < 1e-9 & abs(H(:) - cfg.drop.height_m) < 1e-9;
rep.fractionResolvableAtPlaceholders = mean(resolvable(sel));   % NaN if config values are not on the grid
rep.slitOnlyResolvable = mean(resolvable(B(:)==0));
rep.evidence = chute.util.evidenceLabel('L2');
rep.note = ['Design spread depends on the assumed aerodynamics; this sweep shows the range of ', ...
    'outcomes, not which design wins. noiseSd from the pipeline validation runs.'];
if ~exist(opts.outDir, 'dir'), mkdir(opts.outDir); end
writetable(T, fullfile(opts.outDir, 'feasibility_sweep.csv'));
fig = figure('Visible', 'off', 'Position', [0 0 900 420]);
tiledlayout(1,2);
nexttile;
gs = findgroups(T.mass_kg, T.height_m);
boxchart(categorical(gs), T.designSpread); hold on; yline(4*se, 'r--', '4 \times SE');
xlabel('(mass, height) group'); ylabel('landing-speed spread across designs (m/s)');
lbl = splitapply(@(m,h) sprintf('%.2fkg/%.1fm', m(1), h(1)), T.mass_kg, T.height_m, gs);
xticklabels(lbl); title('Spread over aero assumptions');
nexttile;
scatter(T.slitStrength + 0.08*randn(height(T),1), T.designSpread, 12, T.cdScale, 'filled');
xlabel('slit-effect strength (0 none, 1 prior, 3 strong)'); ylabel('design spread (m/s)'); colorbar; title('colour = C_D scale');
sgtitle({'Feasibility sweep', rep.evidence}, 'FontSize', 10);
exportgraphics(fig, fullfile(opts.outDir, 'feasibility_sweep.png')); close(fig);
fid = fopen(fullfile(opts.outDir, 'summary.txt'), 'w');
fprintf(fid, '%s\nfraction of assumption sets resolvable: %.2f\nat placeholder mass/height: %.2f\nwith no slit effect: %.2f\nper-drop noise sd %.3f m/s, repeats %d\n%s\n', ...
    rep.evidence, rep.fractionResolvable, rep.fractionResolvableAtPlaceholders, rep.slitOnlyResolvable, opts.noiseSd, opts.repeats, rep.note);
fclose(fid);
end
