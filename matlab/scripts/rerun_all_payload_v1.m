%RERUN_ALL_PAYLOAD_V1 Rerun tests, feasibility (80-105 g, 4-6 m) and DOE for payload V1.
run(fullfile(fileparts(mfilename('fullpath')), 'setupPaths.m'));
root = chute.util.repoRoot();
res = runtests(fullfile(root, 'matlab', 'tests'));
disp(table(res));
fprintf('MATLAB TESTS: %d passed, %d failed\n', nnz([res.Passed]), nnz([res.Failed]));
D = chute.doe.lhsDesigns(16, 1);
rep = chute.ode.feasibilitySweep(designs=D, outDir=fullfile(root, 'results', 'feasibility_v3_payloadV1'));
T = rep.table;
G = groupsummary(T, {'mass_kg','height_m'}, {'mean','median','max'}, {'meanLandingSpeed','designSpread'});
R = groupsummary(T, {'mass_kg','height_m'}, 'sum', 'resolvable');
writetable(G, fullfile(root, 'results', 'feasibility_v3_payloadV1', 'by_mass_height.csv'));
writetable(R, fullfile(root, 'results', 'feasibility_v3_payloadV1', 'resolvable_by_mass_height.csv'));
S = groupsummary(T, 'slitStrength', 'sum', 'resolvable');
writetable(S, fullfile(root, 'results', 'feasibility_v3_payloadV1', 'resolvable_by_slit_strength.csv'));
disp(G); disp(R); disp(S);
fprintf('overall resolvable %.3f, at config mass/height %.3f\n', rep.fractionResolvable, rep.fractionResolvableAtPlaceholders);
run(fullfile(root, 'matlab', 'scripts', 'm7_doe.m'));
