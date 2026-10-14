%M10_STUDIES Milestone 10: representation (PCA / AE / VAE), surrogate comparison with
%leave-geometry-out CV, Sobol sensitivity on the best surrogate, k-means/PCA on flight features.
% Uses whatever simulator evaluations exist in the cache (L2).
run(fullfile(fileparts(mfilename('fullpath')), 'setupPaths.m'));
if ~exist('OUT_SUBDIR', 'var'), OUT_SUBDIR = 'studies'; end
out = fullfile(chute.util.repoRoot(), 'results', OUT_SUBDIR);
if ~exist(out, 'dir'), mkdir(out); end
L2 = chute.util.evidenceLabel('L2');
if ~exist('SKIP_REP', 'var') || ~SKIP_REP
% --- representation ---
[R, info] = chute.rep.shapeDataset(3000, 1);
R = R(info.valid, :);
P = chute.rep.pcaStudy(R); writetable(P.table, fullfile(out, 'rep_pca.csv'));
A = chute.rep.aeStudy(R, [2 3 4 6 8], epochs=150); writetable(A.table, fullfile(out, 'rep_ae.csv'));
V = chute.rep.vaeStudy(R, 4, epochs=150);
fid = fopen(fullfile(out, 'rep_vae.txt'), 'w');
fprintf(fid, 'VAE k=4: generated valid rate %.3f, diversity %.3f (data %.3f)\n', V.validRate, V.diversity, V.dataDiversity); fclose(fid);
% --- same search, same budget, different representations (simulator + sensing pipeline, L2) ---
if ~exist('SKIP_LATENT', 'var') || ~SKIP_LATENT
    LS = chute.rep.latentSearch(R, P, A, V, k=4, budget=50, nRuns=3, nScenarios=3, method='bo');
    writetable(LS, fullfile(out, 'latent_search.csv'));
    disp(groupsummary(LS, 'representation', {'median','mean'}, {'best_score','valid_geometry_rate'}));
end
end
% --- flight features from the evaluation cache ---
if exist('REP_ONLY', 'var') && REP_ONLY, return; end
ffile = fullfile(out, 'flight_features.csv');
chute.bridge.call('flight_features_csv', ffile, '', 'fused');
T = readtable(ffile);
fn = {'preimpact_vz','lateral_speed','landing_offset','tilt_rms_deg','tilt_max_deg','swing_rate_rms','peak_specific_force_g'};
ok = all(~ismissing(T(:, fn)), 2);
T = T(ok, :);
fprintf('%d drops with complete sensor-derived features\n', height(T));
if height(T) >= 12
    % surrogates on per-design means (scenario average), at most 1500 designs
    [gid, q_, l_, r_] = findgroups(T.q, T.slit_len, T.slit_r);
    X = [q_ l_ r_]; y = splitapply(@mean, T.preimpact_vz, gid);
    rng(0); if size(X,1) > 1500, sel = randperm(size(X,1), 1500); X = X(sel,:); y = y(sel); end
    C = chute.surrogate.leaveGeometryOutCV(X, y, (1:size(X,1))', {'linear','quadratic','gp','ensemble'}, 10);
    writetable(C, fullfile(out, 'surrogate_cv.csv')); disp(C);
    M = chute.surrogate.fitModels(X, y, {'gp'});
    [lb, ub] = chute.doe.bounds();
    S = chute.analysis.sobolIndices(@(Z) predict(M.gp, Z), lb, ub, 4000);
    writetable(table(["q";"slit_len";"slit_r"], S.first', S.total', 'VariableNames', {'var','first','total'}), fullfile(out, 'sobol.csv'));
    chute.analysis.interactionPlot(@(Z) predict(M.gp, Z), lb, ub, {'q','slit len','slit r'}, fullfile(out, 'interactions.png'), L2);
    rng(0); Fsub = T{:, fn}; if size(Fsub,1) > 3000, Fsub = Fsub(randperm(size(Fsub,1), 3000), :); end
    K = chute.analysis.flightClusters(Fsub, fn);
    writetable(K.centroids, fullfile(out, 'flight_clusters.csv'));
    fprintf('k-means: k=%d silhouette %.2f (meaningful=%d); PCA needs %d comps for 90%%\n', K.k, K.bestSilhouette, K.meaningful, K.pca.nFor90);
end
