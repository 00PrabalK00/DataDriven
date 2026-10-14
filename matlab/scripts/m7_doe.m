%M7_DOE Milestone 7: initial experimental design, randomized drop schedule, 1:1 cutting templates.
run(fullfile(fileparts(mfilename('fullpath')), 'setupPaths.m'));
out = fullfile(chute.util.repoRoot(), 'results', 'doe');
if ~exist(out, 'dir'), mkdir(out); end
[D, info] = chute.doe.lhsDesigns(16, 1);
T = table((1:size(D,1))', D(:,1), D(:,2), D(:,3), info.isBaseline, 'VariableNames', {'design','q','slit_len','slit_r','baseline'});
writetable(T, fullfile(out, 'designs.csv'));
S = chute.doe.dropSchedule(D, info.isBaseline, 3, 2026);
writetable(S, fullfile(out, 'drop_schedule.csv'));
for i = 1:size(D,1)
    chute.geom.exportTemplate(D(i,1), D(i,2), D(i,3), fullfile(out, 'templates'), sprintf('design%02d', i));
end
fprintf('designs: %d (centered L2 discrepancy %.4f, min distance %.3f)\n', size(D,1), info.discrepancy, info.minDistance);
fprintf('schedule: %d drops -> %s\n', height(S), fullfile(out, 'drop_schedule.csv'));
