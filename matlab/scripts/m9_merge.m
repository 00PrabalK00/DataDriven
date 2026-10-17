%M9_MERGE Combine the full-benchmark shards into one results table + convergence plot (L2).
run(fullfile(fileparts(mfilename('fullpath')), 'setupPaths.m'));
d = fullfile(chute.util.repoRoot(), 'results', 'benchmark_full');
files = [dir(fullfile(d, 'full_shard*_runs.mat')); dir(fullfile(d, 'jobs', 'full_job_*_runs.mat'))];
runs = {};
for f = files'
    S = load(fullfile(f.folder, f.name), 'runs');
    runs = [runs, S.runs]; %#ok<AGROW>
end
fprintf('%d runs merged from %d files\n', numel(runs), numel(files));
isMoo = cellfun(@(r) strcmp(r.method, 'moo'), runs);
T = chute.bench.summarize(runs(~isMoo), 200);
writetable(T, fullfile(d, 'full_summary.csv')); disp(T);
lab = sprintf('%s | simulator (5 fixed scenarios, common random numbers), payload V1, 4 m', chute.util.evidenceLabel('L2'));
chute.bench.convergencePlot(runs(~isMoo), 200, fullfile(d, 'full_convergence.png'), lab);
if any(isMoo)
    Tm = chute.bench.summarize(runs(isMoo), 200);
    writetable(Tm, fullfile(d, 'moo_summary.csv')); disp(Tm);
end
save(fullfile(d, 'full_merged.mat'), 'runs', 'T');
