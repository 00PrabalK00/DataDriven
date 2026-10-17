%M10_LATENT Latent-space search study only (same BO search and budget in the 3-parameter encoding vs the
%PCA / AE / VAE latent spaces of free-form outlines). Set NRUNS (default 3) before running.
% Reuses the trained representation models saved by m10_studies (results/studies/rep_models.mat) if present.
run(fullfile(fileparts(mfilename('fullpath')), 'setupPaths.m'));
if ~exist('NRUNS', 'var'), NRUNS = 3; end
out = fullfile(chute.util.repoRoot(), 'results', 'studies');
[R, info] = chute.rep.shapeDataset(3000, 1);
R = R(info.valid, :);
mf = fullfile(out, 'rep_models.mat');
S = struct(); if isfile(mf), S = load(mf); end
if all(isfield(S, {'P', 'A', 'V'}))
    P = S.P; A = S.A; V = S.V; disp('reusing saved representation models');
else
    P = chute.rep.pcaStudy(R); A = chute.rep.aeStudy(R, [2 3 4 6 8], epochs=150); V = chute.rep.vaeStudy(R, 4, epochs=150);
end
LS = chute.rep.latentSearch(R, P, A, V, k=4, budget=50, nRuns=NRUNS, nScenarios=3, method='bo');
writetable(LS, fullfile(out, 'latent_search.csv'));
disp(groupsummary(LS, 'representation', {'median','mean'}, {'best_score','valid_geometry_rate'}));
